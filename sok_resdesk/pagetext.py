"""Page text versions: re-OCR and proofreading.

A page's text starts as archive.org's OCR (kept in the page-text cache, not here). A new OCR of
the page (reocr.py) or a person's correction is saved as an RD Page Text version; the page's
current version is what the reader shows, search finds and citations quote, wherever the page's
text is read (ingest.fetch_pages lays the current versions over archive.org's text). Re-ingesting
a book from archive.org never undoes a correction.

* **Machine**: a re-OCR nobody has checked. It replaces archive.org's text only if it scores
  better (core/ocrquality.py), and never replaces a person's work.
* **Proofread**: corrected by a proofreader (or staff).
* **Validated**: checked again, unchanged, by a second person.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, now_datetime

from sok_resdesk.core import ocrquality
from sok_resdesk.core import zones as zn

DT = "RD Page Text"
PROOFREADERS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer", "ResDesk Proofreader")
HUMAN = ("Proofread", "Validated")


def can_proofread(user: str | None = None) -> bool:
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(PROOFREADERS))


def current(item_id: str) -> dict[int, dict]:
	"""{leaf: version} of the book's current versions (most books: none)."""
	rows = frappe.get_all(
		DT,
		filters={"item": item_id, "is_current": 1},
		fields=[
			"name",
			"leaf",
			"page_label",
			"text",
			"status",
			"source",
			"proofread_by",
			"validated_by",
			"engine",
		],
	)
	return {cint(r.leaf): r for r in rows}


def apply(item_id: str, pages: list[dict]) -> list[dict]:
	"""archive.org's pages with the current versions laid over them (called by fetch_pages)."""
	try:
		versions = current(item_id)
	except Exception:
		return pages  # e.g. during install, before the table exists
	if not versions:
		return pages
	by_leaf = {p["leaf"]: dict(p) for p in pages}
	for leaf, v in versions.items():
		page = by_leaf.setdefault(leaf, {"leaf": leaf, "label": v.page_label or ""})
		page["text"] = v.text or ""
		page["status"] = v.status
	return [by_leaf[k] for k in sorted(by_leaf)]


def save(
	item_id: str,
	leaf: int,
	text: str,
	source: str,
	status: str,
	zones: list | None = None,
	engine: str = "",
	page_label: str = "",
	user: str | None = None,
	reindex: bool = True,
) -> str:
	"""Make `text` the page's current version. Returns the new version's name."""
	user = user or frappe.session.user
	leaf = cint(leaf)
	frappe.db.sql(
		f"update `tab{DT}` set is_current = 0 where item = %s and leaf = %s and is_current = 1",
		(item_id, leaf),
	)
	q = ocrquality.page_quality(text)
	values = {
		"doctype": DT,
		"item": item_id,
		"leaf": leaf,
		"page_label": (page_label or "")[:20],
		"is_current": 1,
		"source": source,
		"status": status,
		"text": text,
		"quality": q["score"] or 0,
		"engine": (engine or "")[:140],
		"zones": json.dumps(zn.clean(zones)) if zones else "",
	}
	if status in HUMAN:
		values.update({"proofread_by": user, "proofread_on": now_datetime()})
	doc = frappe.get_doc(values).insert(ignore_permissions=True)
	_after_change(item_id, leaf, reindex)
	return doc.name


def _after_change(item_id: str, leaf: int, reindex: bool = True) -> None:
	"""The changed page goes to search at once; the book's counts and OCR quality follow."""
	frappe.db.set_value(
		"RD Item",
		item_id,
		"pages_proofread",
		frappe.db.count(DT, {"item": item_id, "is_current": 1, "status": ("in", HUMAN)}),
		update_modified=False,
	)
	if not reindex:
		return
	from sok_resdesk.ingest import fetch_pages
	from sok_resdesk.search import quality_fields, reindex_pages

	pages = fetch_pages(item_id)
	frappe.db.set_value("RD Item", item_id, quality_fields(pages), update_modified=False)
	try:
		reindex_pages(item_id, [p for p in pages if p["leaf"] == leaf])
	except Exception:
		frappe.log_error(title=f"Research Desk: page {leaf} of {item_id} not re-indexed")


# -- the reader's Proofread mode -------------------------------------------------------------------


def _check(item_id: str) -> None:
	from sok_resdesk import access

	if not can_proofread():
		frappe.throw(_("Proofreading is for the library's proofreaders."), frappe.PermissionError)
	vis = frappe.db.get_value("RD Item", item_id, "visibility")
	if vis is None or not access.can_read(vis):
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)


@frappe.whitelist(methods=["GET"])
def history(item_id: str, leaf: int) -> dict:
	"""The page's versions, newest first, and where it stands."""
	_check(item_id)
	rows = frappe.get_all(
		DT,
		filters={"item": item_id, "leaf": cint(leaf)},
		fields=[
			"name",
			"source",
			"status",
			"quality",
			"is_current",
			"proofread_by",
			"validated_by",
			"engine",
			"creation",
			"zones",
		],
		order_by="creation desc",
		limit=50,
	)
	for r in rows:
		r.proofread_by_name = get_fullname(r.proofread_by) if r.proofread_by else ""
		r.validated_by_name = get_fullname(r.validated_by) if r.validated_by else ""
		r.creation = str(r.creation)[:16]
		r.zones = json.loads(r.zones) if r.zones else []
	return {"versions": rows, "presets": zn.presets(), "me": frappe.session.user}


@frappe.whitelist(methods=["POST"])
def save_page(
	item_id: str, leaf: int, text: str, zones=None, page_label: str = "", validate: int = 0
) -> dict:
	"""A proofreader's save. With validate=1 and the text unchanged, a page proofread by someone
	else becomes Validated; otherwise the text becomes a new Proofread version."""
	_check(item_id)
	leaf = cint(leaf)
	text = (text or "").replace("\r\n", "\n")
	if len(text) > 100_000:
		frappe.throw(_("That is more text than a page holds."))
	zones = zn.clean(zones) if zones else None
	now = current(item_id).get(leaf)
	if cint(validate):
		if not now or now.status != "Proofread":
			frappe.throw(_("Only a proofread page can be validated."))
		if now.proofread_by == frappe.session.user:
			frappe.throw(
				_(
					"A page is validated by a second person: you proofread this one, so someone else checks it."
				)
			)
		if (now.text or "").strip() == text.strip():
			frappe.db.set_value(
				DT,
				now.name,
				{"status": "Validated", "validated_by": frappe.session.user, "validated_on": now_datetime()},
			)
			_after_change(item_id, leaf, reindex=False)
			return {"status": "Validated", "name": now.name}
	name = save(item_id, leaf, text, "Proofreading", "Proofread", zones, page_label=page_label)
	return {"status": "Proofread", "name": name}


@frappe.whitelist(methods=["POST"])
def restore(name: str) -> dict:
	"""Make an earlier version current again (as a new version: the history keeps everything)."""
	row = frappe.db.get_value(DT, name, ["item", "leaf", "text", "zones", "page_label"], as_dict=True)
	if not row:
		raise frappe.DoesNotExistError
	_check(row.item)
	new = save(
		row.item,
		row.leaf,
		row.text,
		"Proofreading",
		"Proofread",
		json.loads(row.zones or "[]") or None,
		page_label=row.page_label,
	)
	return {"status": "Proofread", "name": new}
