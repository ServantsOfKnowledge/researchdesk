"""Preservation copies: the library's own verified copy of each book, kept as an OCFL object in
the folder set in Settings → Preservation (core/ocfl.py has the format).

* **What**: Settings → Preservation → *Preserve*: off, the books in collections marked *Preserve*,
  or every book. For an archive.org book: its PDF, OCR (text, hOCR, page index), metadata and
  page numbers, and with *Page Images* the original scans too (much larger). For a book from a
  folder: every file in its folder.
* **How**: each file is fetched once and compared with the md5 archive.org publishes; the book
  becomes a new OCFL version only when a file changed, so a re-ingest costs nothing.
* **Checked**: every night a share of the copies is checked against their checksums, so every
  copy is checked within *Check Every (days)*. A failure is recorded as an event on the book,
  marks it *Failed check* and alerts on the Server page.

Every fetch and every failed check is a Preservation Event (PREMIS-style: what, when, outcome, by
whom). Checks that pass only update the book's *Fixity Checked On*, to keep the list readable.
"""

from __future__ import annotations

import math
import os
import shutil
import tempfile

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from sok_resdesk.core import ocfl
from sok_resdesk.holding import hold_when_paused

MANAGERS = ("System Manager", "ResDesk Manager")
GB = 1024**3
EVERY = "Every book"
IN_COLLECTIONS = "Books in collections marked Preserve"
# archive.org formats kept for every book (the scans themselves only with Page Images)
KEEP_FORMATS = {
	"Metadata",
	"Text PDF",
	"Additional Text PDF",
	"DjVuTXT",
	"Djvu XML",
	"hOCR",
	"OCR Page Index",
	"OCR Search Text",
	"Page Numbers JSON",
	"MARC",
	"MARC Binary",
	"Dublin Core",
}
SKIP_FORMATS = {"Archive BitTorrent", "Item Tile", "JPEG Thumb"}
BATCH = 10


def _settings() -> dict:
	return frappe.db.get_singles_dict("RD Settings")


def root() -> str | None:
	path = (_settings().get("preservation_root") or "").strip()
	return path or None


def enabled() -> bool:
	s = _settings()
	return bool(root()) and (s.get("preserve_books") or "Off") != "Off"


def agent() -> str:
	from sok_resdesk import __version__

	return f"Research Desk {__version__}"


def event(item: str, kind: str, outcome: str, detail: str = "", version: str = "") -> None:
	frappe.get_doc(
		{
			"doctype": "RD Preservation Event",
			"item": item,
			"event_type": kind,
			"outcome": outcome,
			"detail": (detail or "")[:5000],
			"version": version,
			"agent": agent() if frappe.session.user in ("Administrator", "Guest") else frappe.session.user,
			"event_on": now_datetime(),
		}
	).insert(ignore_permissions=True)


# -- which books ----------------------------------------------------------------------------------


def wanted(limit: int = 0) -> list[str]:
	"""Books that should have a copy and have none yet, or were ingested again since their copy."""
	if not enabled():
		return []
	scope = _settings().get("preserve_books")
	join = where = ""
	if scope == IN_COLLECTIONS:
		join = """join `tabRD Item Collection` ic on ic.parent = i.name and ic.parenttype = 'RD Item'
			join `tabRD Collection` c on c.name = ic.collection and c.preserve = 1"""
	where = "(i.preserved_on is null or (i.last_ingested is not null and i.last_ingested > i.preserved_on))"
	return frappe.db.sql_list(
		f"""select distinct i.name, i.creation from `tabRD Item` i {join} where {where}
		order by i.creation asc {"limit %(limit)s" if limit else ""}""",
		{"limit": cint(limit)},
	)


def used_bytes() -> float:
	return flt(frappe.db.sql("select coalesce(sum(preserved_bytes), 0) from `tabRD Item`")[0][0])


def room_left() -> float | None:
	"""Bytes the copies may still take: the budget in Settings, and never the last 5% of the disk."""
	path = root()
	if not path:
		return 0
	budget = cint(_settings().get("preservation_budget_gb")) * GB
	left = budget - used_bytes() if budget else None
	try:
		os.makedirs(path, exist_ok=True)
		du = shutil.disk_usage(path)
		disk_left = du.free - du.total * 0.05
		left = disk_left if left is None else min(left, disk_left)
	except OSError:
		return 0
	return left


# -- making a copy --------------------------------------------------------------------------------


def _ia_files(item_id: str, with_images: bool) -> list[dict]:
	from sok_resdesk.ingest import client

	files = client().metadata(item_id).get("files") or []
	out = []
	for f in files:
		name, fmt = f.get("name") or "", f.get("format") or ""
		# _files.xml changes whenever archive.org touches the item: keeping it would make a new
		# version every time without the book changing
		if not name or fmt in SKIP_FORMATS or name.endswith("_files.xml"):
			continue
		if fmt in KEEP_FORMATS or (with_images and f.get("source") == "original"):
			out.append(f)
	return out


def _fetch_ia(item_id: str, staging: str, with_images: bool) -> dict[str, str]:
	from sok_resdesk.core.ia import IAError
	from sok_resdesk.ingest import client

	ia = client()
	got = {}
	for f in _ia_files(item_id, with_images):
		dest = os.path.join(staging, f"{len(got):05d}")
		info = ia.download_file(item_id, f["name"], dest)
		if f.get("md5") and info["md5"] != f["md5"]:
			raise IAError(f"{f['name']}: the download doesn't match archive.org's md5")
		got[f["name"]] = dest
	if not got:
		raise IAError("archive.org lists no files to keep for this book")
	return got


def _fetch_local(doc, staging: str) -> dict[str, str]:
	from sok_resdesk.local_source import store_for_item

	store = store_for_item(doc)
	if not store or not hasattr(store, "file_path"):
		raise ValueError(
			_("The book's folder can't be read as files (a web server source is copied in a later release).")
		)
	got = {}
	for name in store.list_files(doc.local_path):
		path = store.file_path(doc.local_path, name)
		if path:
			got[name] = path  # copied (not moved) into the object: the folder is the library's own
	if not got:
		raise ValueError(_("No files in the book's folder"))
	return got


def preserve(name: str) -> dict:
	"""Make or update one book's copy. Returns {version, changed, bytes}."""
	path = root()
	if not path:
		frappe.throw(_("Set a folder in Settings → Preservation first."))
	doc = frappe.get_doc("RD Item", name)
	with_images = bool(cint(_settings().get("preserve_page_images")))
	ocfl.init_root(path)
	staging = tempfile.mkdtemp(prefix=".staging-", dir=path)
	try:
		if doc.source == "Local":
			files, move = _fetch_local(doc, staging), False
		else:
			files, move = _fetch_ia(doc.item_id, staging, with_images), True
		from sok_resdesk.catalogue import base_url

		result = ocfl.write_version(
			path,
			doc.item_id,
			files,
			message=f"{doc.source} · {doc.get('persistent_id') or doc.item_id}",
			user=agent(),
			address=base_url(),
			move=move,
		)
	except Exception as e:
		frappe.db.rollback()
		event(name, "Ingestion", "Failure", str(e))
		frappe.db.commit()
		raise
	finally:
		shutil.rmtree(staging, ignore_errors=True)
	check = ocfl.verify(path, doc.item_id)
	frappe.db.set_value(
		"RD Item",
		name,
		{
			"preservation_status": "Preserved" if check["ok"] else "Failed check",
			"preserved_on": now_datetime(),
			"preserved_version": result["version"],
			"preserved_bytes": check["bytes"],
			"fixity_checked_on": now_datetime(),
		},
		update_modified=False,
	)
	if result["changed"] or not check["ok"]:
		files_count = len(ocfl.head_files(path, doc.item_id))
		event(
			name,
			"Ingestion",
			"Success" if check["ok"] else "Failure",
			_("{0} files, {1} new bytes").format(files_count, result["added_bytes"])
			if check["ok"]
			else "; ".join(check["problems"][:20]),
			result["version"],
		)
	frappe.db.commit()
	return {"version": result["version"], "changed": result["changed"], "bytes": check["bytes"]}


@hold_when_paused("long")
def preserve_batch(names: list[str]) -> int:
	done = 0
	for name in names:
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		left = room_left()
		if left is not None and left <= 0:
			frappe.log_error("Research Desk: preservation copies stopped", "No room left (budget or disk)")
			break
		try:
			preserve(name)
			done += 1
		except Exception:
			frappe.db.rollback()  # recorded as a failed Ingestion event; the next turn tries again
	return done


def queue_preservation(limit: int = 500) -> int:
	names = wanted(limit)
	for n, i in enumerate(range(0, len(names), BATCH), 1):
		frappe.enqueue(
			"sok_resdesk.preservation.preserve_batch",
			queue="long",
			timeout=6 * 3600,
			names=names[i : i + BATCH],
			job_id=f"resdesk-preserve-{n}",
		)
	return len(names)


# -- checking the copies --------------------------------------------------------------------------


def check(name: str) -> dict:
	"""Check one book's copy against its checksums; records a failure (or a recovery)."""
	path = root()
	item_id, status = frappe.db.get_value("RD Item", name, ["item_id", "preservation_status"])
	result = ocfl.verify(path, item_id) if path else {"ok": False, "problems": ["no preservation folder"]}
	new_status = (
		"Preserved"
		if result["ok"]
		else ("Missing" if "no inventory.json" in " ".join(result["problems"]) else "Failed check")
	)
	frappe.db.set_value(
		"RD Item",
		name,
		{"preservation_status": new_status, "fixity_checked_on": now_datetime()},
		update_modified=False,
	)
	if not result["ok"]:
		event(name, "Fixity check", "Failure", "\n".join(result["problems"][:50]))
	elif status in ("Failed check", "Missing"):
		event(name, "Fixity check", "Success", _("The copy checks out again"))
	frappe.db.commit()
	return result


def audit(days: int | None = None) -> dict:
	"""Every night: check the copies checked longest ago, enough that each is checked within
	`days` (Settings → Check Every). Failures alert on the Server page."""
	days = max(1, cint(days or _settings().get("fixity_days") or 30))
	total = frappe.db.count("RD Item", {"preserved_on": ("is", "set")})
	if not total or not root():
		return {"checked": 0, "failed": 0}
	names = frappe.get_all(
		"RD Item",
		filters={"preserved_on": ("is", "set")},
		pluck="name",
		order_by="fixity_checked_on asc",
		limit=math.ceil(total / days),
	)
	failed = 0
	for name in names:
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		failed += not check(name)["ok"]
	if failed:
		from sok_resdesk.server import send_alert

		send_alert(
			"preservation",
			"bad",
			_("{0} preservation copies failed their check: see Preservation Events.").format(failed),
			link="/app/rd-preservation-event?outcome=Failure",
		)
	return {"checked": len(names), "failed": failed}


def daily() -> None:
	"""Scheduler: copy what is waiting (a few hundred books a night), then check the copies."""
	if not root():
		return
	if enabled():
		queue_preservation()
	frappe.enqueue(
		"sok_resdesk.preservation.audit", queue="long", timeout=6 * 3600, job_id="resdesk-fixity-audit"
	)


# -- the Desk -------------------------------------------------------------------------------------


@frappe.whitelist()
def preserve_now(item: str) -> dict:
	"""Book form → Preserve Now (whatever the scope in Settings)."""
	frappe.only_for(MANAGERS)
	return preserve(item)


@frappe.whitelist()
def check_now(item: str) -> dict:
	frappe.only_for(MANAGERS)
	return check(item)


@frappe.whitelist()
def enqueue_preservation() -> int:
	frappe.only_for(MANAGERS)
	if not enabled():
		frappe.throw(_("Set a folder and what to preserve in Settings → Preservation first."))
	return queue_preservation(limit=0)


def health_check() -> dict:
	"""For the Server page."""
	if not root():
		return {
			"key": "preservation",
			"label": _("Preservation copies"),
			"state": "off",
			"detail": _("off"),
			"link": "/app/rd-settings",
		}
	counts = dict(
		frappe.db.sql(
			"select preservation_status, count(*) from `tabRD Item` where preserved_on is not null group by preservation_status"
		)
	)
	bad = cint(counts.get("Failed check")) + cint(counts.get("Missing"))
	kept = sum(cint(v) for v in counts.values())
	detail = _("{0} books, {1} GB").format(f"{kept:,}", round(used_bytes() / GB, 1))
	return {
		"key": "preservation",
		"label": _("Preservation copies"),
		"state": "bad" if bad else "ok",
		"detail": detail + (" · " + _("{0} failed their check").format(bad) if bad else ""),
		"link": "/app/rd-preservation-event?outcome=Failure" if bad else "/app/rd-settings",
	}
