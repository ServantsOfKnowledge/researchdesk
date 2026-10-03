"""Ground truth: proofread pages with their images, shared as an open set for training OCR.

Staff make a set in the Desk (Ground Truth → New: which pages, which books), and it is built in
the background into a zip (core/groundtruth.py) in the site's private files. A set can go on the
portal (`/library/ground-truth`) for anyone to download only once the library has chosen a
licence for its corrected texts (Settings → Ground Truth), and only from books anyone may read.
Until then sets are for the library's own use: testing OCR engines on its own pages.
"""

from __future__ import annotations

import hashlib
import json
import os

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, now_datetime

from sok_resdesk.core import groundtruth as core

DT = "RD Ground Truth"
MANAGERS = ("System Manager", "ResDesk Manager")
STAFF = (*MANAGERS, "ResDesk Cataloguer")


def folder() -> str:
	return frappe.get_site_path("private", "ground-truth")


def chosen_licence() -> str:
	return (frappe.db.get_single_value("RD Settings", "ground_truth_licence") or "").strip()


def check_set(doc) -> None:
	"""RD Ground Truth.validate: a set on the portal needs a licence and books anyone may read."""
	doc.max_pages = max(1, min(cint(doc.max_pages) or 5000, 100_000))
	doc.language = (doc.language or "").strip().lower()
	if doc.published and not (doc.licence and cint(doc.public_books_only)):
		doc.published = 0


def _pages_query(doc, count_only: bool = False):
	where = ["t.is_current = 1", "i.published = 1"]
	params: dict = {}
	if doc.pages_wanted == "Validated only":
		where.append("t.status = 'Validated'")
	else:
		where.append("t.status in ('Proofread', 'Validated')")
	if doc.item:
		where.append("t.item = %(item)s")
		params["item"] = doc.item
	if doc.language:
		where.append("(i.language = %(language)s or i.language like %(language_like)s)")
		params.update({"language": doc.language, "language_like": f"%{doc.language}%"})
	if doc.collection:
		where.append(
			"""exists (select 1 from `tabRD Item Collection` c where c.parent = i.name
			and c.parenttype = 'RD Item' and c.collection = %(collection)s)"""
		)
		params["collection"] = doc.collection
	if cint(doc.public_books_only):
		where.append("ifnull(i.visibility, 'Public') = 'Public'")
	if count_only:
		return frappe.db.sql(
			f"""select count(*) from `tabRD Page Text` t join `tabRD Item` i on i.name = t.item
			where {" and ".join(where)}""",
			params,
		)[0][0]
	params["limit"] = cint(doc.max_pages) or 5000
	return frappe.db.sql(
		f"""select t.item, t.leaf, t.page_label, t.text, t.zones, t.status, t.source, t.quality,
		t.proofread_by, t.validated_by, i.title, i.language, i.persistent_id
		from `tabRD Page Text` t join `tabRD Item` i on i.name = t.item
		where {" and ".join(where)} order by t.item, t.leaf limit %(limit)s""",
		params,
		as_dict=True,
	)


@frappe.whitelist()
def preview(name: str) -> dict:
	"""How many pages the set would hold now, and the licence it would carry."""
	frappe.only_for(STAFF)
	doc = frappe.get_doc(DT, name)
	return {
		"pages": min(_pages_query(doc, count_only=True), cint(doc.max_pages) or 5000),
		"licence": chosen_licence(),
	}


@frappe.whitelist(methods=["POST"])
def build(name: str) -> dict:
	"""Make (or make again) the set's zip, in the background."""
	frappe.only_for(MANAGERS)
	doc = frappe.get_doc(DT, name)
	if doc.status in ("Queued", "Running"):
		frappe.throw(_("This set is being made already."))
	if not _pages_query(doc, count_only=True):
		frappe.throw(_("No proofread pages match yet: proofread some pages of these books first."))
	doc.db_set({"status": "Queued", "log": ""})
	frappe.enqueue(
		"sok_resdesk.groundtruth.build_job",
		queue="long",
		timeout=24 * 3600,
		name=name,
		user=frappe.session.user,
		enqueue_after_commit=True,
	)
	return {"queued": True}


def _who(user: str | None, names: bool, cache: dict) -> str:
	if not names or not user:
		return ""
	if user not in cache:
		full = get_fullname(user) or ""
		cache[user] = "" if "@" in full else full  # a name, never an email
	return cache[user]


def build_job(name: str, user: str | None = None) -> None:
	from sok_resdesk.catalogue import base_url, settings
	from sok_resdesk.core import citations
	from sok_resdesk.reocr import page_image

	doc = frappe.get_doc(DT, name)
	log: list[str] = []
	doc.db_set({"status": "Running", "log": ""})
	frappe.db.commit()
	try:
		s = settings()
		names = bool(cint(s.get("ground_truth_names")))
		people: dict = {}
		url = base_url()
		pages = []
		for r in _pages_query(doc):
			record = {"item_id": r.item, "persistent_id": r.persistent_id}
			pages.append(
				{
					"item": r.item,
					"title": r.title,
					"leaf": cint(r.leaf),
					"page_label": r.page_label,
					"text": r.text or "",
					"zones": json.loads(r.zones) if r.zones else None,
					"language": r.language,
					"status": r.status,
					"source": r.source,
					"quality": r.quality,
					"proofread_by": _who(r.proofread_by, names, people),
					"validated_by": _who(r.validated_by, names, people),
					"page_url": citations.with_page(record, cint(r.leaf), "", url)["page_url"],
				}
			)
		os.makedirs(folder(), exist_ok=True)
		file_name = f"{frappe.scrub(doc.title)[:60] or 'ground-truth'}-{doc.name}.zip"
		path = os.path.join(folder(), file_name)
		licence = chosen_licence()
		meta = {
			"name": doc.name,
			"title": doc.title,
			"organisation": s.get("portal_title") or "Research Desk",
			"url": url,
			"licence": licence or None,
			"attribution": s.get("ground_truth_attribution") or "",
			"created": now_datetime().strftime("%Y-%m-%d"),
			"validated_only": doc.pages_wanted == "Validated only",
		}
		counts = core.write(
			path + ".part", pages, page_image, meta, bool(cint(doc.include_zones)), log.append
		)
		os.replace(path + ".part", path)
		if doc.file_name and doc.file_name != file_name:
			remove_file(doc)
		doc.db_set(
			{
				"status": "Ready",
				"licence": licence,
				"published": doc.published if licence else 0,
				"made_on": now_datetime(),
				"page_count": counts["pages"],
				"zone_count": counts["zones"],
				"book_count": counts["books"],
				"languages": ", ".join(counts["languages"])[:140],
				"file_name": file_name,
				"file_size": _size(os.path.getsize(path)),
				"sha256": _sha256(path),
				"log": "\n".join(log[-500:])
				+ (f"\n{counts['skipped']} pages left out" if counts["skipped"] else ""),
			}
		)
		subject = _("Ground truth ready: {0} ({1} pages)").format(doc.title, counts["pages"])
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Research Desk: ground truth {name} failed")
		doc.db_set({"status": "Failed", "log": "\n".join([*log[-200:], str(e)[:1000]])})
		subject = _("Ground truth {0} failed: {1}").format(doc.title, str(e)[:200])
	if user:
		try:
			frappe.get_doc(
				{"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": subject}
			).insert(ignore_permissions=True)
		except Exception:
			pass
	frappe.db.commit()


def _sha256(path: str) -> str:
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(1 << 20), b""):
			h.update(block)
	return h.hexdigest()


def _size(n: int) -> str:
	for unit in ("bytes", "KB", "MB", "GB"):
		if n < 1024 or unit == "GB":
			return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
		n /= 1024
	return ""


def remove_file(doc) -> None:
	if doc.file_name and "/" not in doc.file_name:
		path = os.path.join(folder(), doc.file_name)
		if os.path.isfile(path):
			os.remove(path)


@frappe.whitelist(methods=["POST"])
def publish(name: str, on: int = 1) -> dict:
	"""Put a ready set on the portal (or take it off)."""
	frappe.only_for(MANAGERS)
	doc = frappe.get_doc(DT, name)
	on = cint(on)
	if on:
		if doc.status != "Ready":
			frappe.throw(_("Make the set first."))
		if not doc.licence:
			frappe.throw(
				_(
					"Choose a licence in Settings → Ground Truth, then make the set again: "
					"a set without one is for the library's own use."
				)
			)
		if not cint(doc.public_books_only):
			frappe.throw(
				_("A set on the portal can hold only books anyone may read: tick that and make it again.")
			)
	doc.db_set("published", on)
	return {"published": on}


def public_sets() -> list[dict]:
	"""The sets on the portal, newest first (for /library/ground-truth)."""
	if not chosen_licence():
		return []
	rows = frappe.get_all(
		DT,
		filters={"published": 1, "status": "Ready"},
		fields=[
			"name",
			"title",
			"licence",
			"made_on",
			"page_count",
			"zone_count",
			"book_count",
			"languages",
			"file_size",
			"sha256",
		],
		order_by="made_on desc",
	)
	for r in rows:
		lic = core.licence(r.licence)
		r.licence_name = lic["name"] if lic else ""
		r.licence_url = lic["url"] if lic else ""
		r.download = f"/api/method/sok_resdesk.groundtruth.download?name={r.name}"
	return rows


@frappe.whitelist(allow_guest=True, methods=["GET"])
def download(name: str):
	"""The set's zip: anyone for a set on the portal, staff for any set."""
	from werkzeug.utils import send_file

	doc = frappe.db.get_value(DT, name, ["name", "status", "published", "licence", "file_name"], as_dict=True)
	if not doc or doc.status != "Ready" or not doc.file_name:
		raise frappe.DoesNotExistError
	public = cint(doc.published) and doc.licence and chosen_licence()
	if not public and not set(frappe.get_roles()) & set(STAFF):
		raise frappe.PermissionError
	path = os.path.join(folder(), doc.file_name)
	if "/" in doc.file_name or not os.path.isfile(path):
		raise frappe.DoesNotExistError
	return send_file(
		path, frappe.local.request.environ, conditional=True, as_attachment=True, download_name=doc.file_name
	)


def counts() -> dict:
	"""For the dashboard and Requirements: pages ready to share."""
	return {
		"validated": frappe.db.count("RD Page Text", {"is_current": 1, "status": "Validated"}),
		"proofread": frappe.db.count(
			"RD Page Text", {"is_current": 1, "status": ("in", ("Proofread", "Validated"))}
		),
		"sets": frappe.db.count(DT, {"status": "Ready"}),
		"public": frappe.db.count(DT, {"status": "Ready", "published": 1}),
	}
