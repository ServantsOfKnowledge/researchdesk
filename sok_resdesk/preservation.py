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

* **A second copy** (Settings → Second Copy): another folder (a disk, a NAS, a partner's storage
  mounted here) or an S3-compatible bucket (core/replica.py). Made right after the first, checked
  on the same schedule; when one copy fails its check and the other is good, the bad one is
  rebuilt from the good one (Repair).
* **Serving from our copy**: when archive.org no longer serves a book we hold, the portal can keep
  it and serve its PDF from our copy (Settings, or book by book from the form).

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

from sok_resdesk import features
from sok_resdesk.core import ocfl
from sok_resdesk.core.replica import FolderReplica, Replica, S3Replica
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


# -- the second copy ------------------------------------------------------------------------------


def second() -> Replica | None:
	"""The second copy's store, when one is set in Settings."""
	s = _settings()
	kind = s.get("second_copy") or "Off"
	if kind == "Folder" and (s.get("second_folder") or "").strip():
		return FolderReplica(s["second_folder"].strip())
	if kind == "S3-compatible" and (s.get("s3_bucket") or "").strip():
		return S3Replica(_s3_client(s), s["s3_bucket"].strip(), (s.get("s3_prefix") or "").strip())
	return None


def _s3_client(s: dict):
	try:
		import boto3
		from botocore.config import Config
	except ImportError:
		frappe.throw(
			_("An S3 second copy needs the boto3 package: run the upgrade again, or pip install boto3.")
		)
	from frappe.utils.password import get_decrypted_password

	try:
		# checksums only where the service needs them: some S3-compatible services refuse the newer
		# default ones; each file still goes up with its MD5 (core/replica.py)
		config = Config(
			request_checksum_calculation="when_required", response_checksum_validation="when_required"
		)
	except TypeError:
		config = Config()
	args = {
		"aws_access_key_id": (s.get("s3_access_key") or "").strip() or None,
		"aws_secret_access_key": get_decrypted_password(
			"RD Settings", "RD Settings", "s3_secret_key", raise_exception=False
		),
		"config": config,
	}
	if (s.get("s3_endpoint") or "").strip():
		args["endpoint_url"] = s["s3_endpoint"].strip()
	if (s.get("s3_region") or "").strip():
		args["region_name"] = s["s3_region"].strip()
	return boto3.client("s3", **args)


def validate_settings(s) -> None:
	"""RD Settings.validate: a second folder must really be somewhere else."""
	if (s.get("second_copy") or "Off") == "Folder":
		folder = (s.get("second_folder") or "").strip()
		if not folder:
			frappe.throw(_("Give the second copy's folder."))
		first = os.path.realpath((s.get("preservation_root") or "").strip() or "/nonexistent")
		second_path = os.path.realpath(folder)
		if (
			second_path == first
			or second_path.startswith(first + os.sep)
			or first.startswith(second_path + os.sep)
		):
			frappe.throw(_("The second copy must be in a different folder from the first, not inside it."))
	if (s.get("second_copy") or "Off") == "S3-compatible":
		for field, label in (("s3_bucket", _("S3 Bucket")), ("s3_access_key", _("S3 Access Key"))):
			if not (s.get(field) or "").strip():
				frappe.throw(_("Give the {0} for the second copy.").format(label))
		if (s.get("s3_endpoint") or "").strip() and not s.s3_endpoint.strip().startswith("https://"):
			frappe.throw(_("The S3 endpoint must start with https://"))


def copies_text(row: dict) -> str:
	"""'2 of 2 verified', '1 of 2 verified', '1 of 1 verified' or ''."""
	if not row.get("preserved_on"):
		return ""
	have, good = 1, int(row.get("preservation_status") == "Preserved")
	if second() is not None or row.get("second_copy_status"):
		have += 1
		good += int(row.get("second_copy_status") == "Copied")
	return _("{0} of {1} verified").format(good, have)


def _update_copies(name: str) -> None:
	row = frappe.db.get_value(
		"RD Item", name, ["preserved_on", "preservation_status", "second_copy_status"], as_dict=True
	)
	frappe.db.set_value("RD Item", name, "copies", copies_text(row or {}), update_modified=False)


def replicate(name: str) -> dict:
	"""Make or bring up to date one book's second copy (from its first copy, checked first)."""
	path, rep = root(), second()
	if not path or rep is None:
		frappe.throw(_("Set a second copy in Settings → Preservation first."))
	doc = frappe.db.get_value(
		"RD Item", name, ["item_id", "preserved_version", "preservation_status"], as_dict=True
	)
	if not doc.preserved_version:
		frappe.throw(_("This book has no first copy yet: Preserve Now first."))
	if not ocfl.verify(path, doc.item_id)["ok"]:
		frappe.throw(
			_("The first copy doesn't pass its check, so it isn't copied: Check Copy repairs it first.")
		)
	where = f"{rep.kind} {rep.describe()}"
	try:
		sent = rep.push(path, doc.item_id)
		result = rep.verify(doc.item_id)
	except Exception as e:
		frappe.db.rollback()
		event(name, "Replication", "Failure", f"{where}: {e}"[:5000])
		frappe.db.set_value("RD Item", name, "second_copy_status", "Failed check", update_modified=False)
		_update_copies(name)
		frappe.db.commit()
		raise
	frappe.db.set_value(
		"RD Item",
		name,
		{
			"second_copy_status": "Copied" if result["ok"] else "Failed check",
			"second_copy_version": doc.preserved_version,
			"second_copy_on": now_datetime(),
			"second_copy_checked_on": now_datetime(),
		},
		update_modified=False,
	)
	if sent["bytes"] or not result["ok"]:
		event(
			name,
			"Replication",
			"Success" if result["ok"] else "Failure",
			_("{0}: {1} bytes sent").format(where, f"{sent['bytes']:,}")
			if result["ok"]
			else f"{where}: " + "; ".join(result["problems"][:20]),
			doc.preserved_version,
		)
	_update_copies(name)
	frappe.db.commit()
	return {"ok": result["ok"], "bytes": sent["bytes"], "where": where}


def wanted_second(limit: int = 0) -> list[str]:
	"""Books whose first copy is good and whose second copy is missing or behind it."""
	if second() is None:
		return []
	return frappe.db.sql_list(
		f"""select name from `tabRD Item` where preservation_status = 'Preserved'
		and ifnull(second_copy_version, '') != ifnull(preserved_version, '')
		order by preserved_on asc {"limit %(limit)s" if limit else ""}""",
		{"limit": cint(limit)},
	)


@hold_when_paused("long")
def replicate_batch(names: list[str]) -> int:
	done = 0
	for name in names:
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		try:
			replicate(name)
			done += 1
		except Exception:
			frappe.db.rollback()  # recorded as a failed Replication event; tried again tomorrow
	return done


def queue_second(limit: int = 500) -> int:
	names = wanted_second(limit)
	for n, i in enumerate(range(0, len(names), BATCH), 1):
		frappe.enqueue(
			"sok_resdesk.preservation.replicate_batch",
			queue="long",
			timeout=6 * 3600,
			names=names[i : i + BATCH],
			job_id=f"resdesk-second-copy-{n}",
		)
	return len(names)


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
	_update_copies(name)
	frappe.db.commit()
	if check["ok"] and second() is not None:
		try:
			replicate(name)  # the second copy follows the first at once
		except Exception:
			frappe.db.rollback()  # recorded as an event; the nightly run tries again
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
	"""Check one book's copies against their checksums. When one fails and the other is good, the
	bad one is rebuilt from the good one (Repair). Records failures, repairs and recoveries."""
	path, rep = root(), second()
	row = frappe.db.get_value(
		"RD Item", name, ["item_id", "preservation_status", "second_copy_status"], as_dict=True
	)
	item_id = row.item_id
	first = ocfl.verify(path, item_id) if path else {"ok": False, "problems": ["no preservation folder"]}
	other = None
	if rep is not None and row.second_copy_status:
		try:
			other = rep.verify(item_id)
		except Exception as e:
			other = {"ok": False, "problems": [f"the second copy can't be read: {e}"]}
	where = f"{rep.kind} {rep.describe()}" if rep is not None else ""
	# repair what the other copy can rebuild
	if path and not first["ok"] and other and other["ok"]:
		try:
			rep.restore(path, item_id)
			event(
				name,
				"Repair",
				"Success",
				_("The first copy was rebuilt from the second ({0}): {1}").format(
					where, "; ".join(first["problems"][:10])
				),
			)
			first = ocfl.verify(path, item_id)
		except Exception as e:
			event(
				name,
				"Repair",
				"Failure",
				_("The first copy could not be rebuilt from the second: {0}").format(e),
			)
	elif first["ok"] and other is not None and not other["ok"]:
		try:
			other = rep.repair(path, item_id)
			event(
				name,
				"Repair",
				"Success" if other["ok"] else "Failure",
				_("The second copy ({0}) was rebuilt from the first").format(where),
			)
		except Exception as e:
			event(
				name,
				"Repair",
				"Failure",
				_("The second copy ({0}) could not be rebuilt: {1}").format(where, e),
			)
	new_status = (
		"Preserved"
		if first["ok"]
		else ("Missing" if "no inventory.json" in " ".join(first["problems"]) else "Failed check")
	)
	values = {"preservation_status": new_status, "fixity_checked_on": now_datetime()}
	if other is not None:
		values["second_copy_status"] = (
			"Copied"
			if other["ok"]
			else ("Missing" if "no inventory.json" in " ".join(other["problems"]) else "Failed check")
		)
		values["second_copy_checked_on"] = now_datetime()
	frappe.db.set_value("RD Item", name, values, update_modified=False)
	if not first["ok"]:
		event(name, "Fixity check", "Failure", "\n".join(first["problems"][:50]))
	elif row.preservation_status in ("Failed check", "Missing"):
		event(name, "Fixity check", "Success", _("The copy checks out again"))
	if other is not None and not other["ok"]:
		event(name, "Fixity check", "Failure", f"{where}: " + "\n".join(other["problems"][:50]))
	_update_copies(name)
	frappe.db.commit()
	return {**first, "second": other}


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


@features.scheduled("preservation")
def daily() -> None:
	"""Scheduler: copy what is waiting (a few hundred books a night), then check the copies."""
	if not root():
		return
	if enabled():
		queue_preservation()
	if second() is not None:
		queue_second()
	frappe.enqueue(
		"sok_resdesk.preservation.audit", queue="long", timeout=6 * 3600, job_id="resdesk-fixity-audit"
	)


# -- the Desk -------------------------------------------------------------------------------------


@frappe.whitelist()
@features.needs("preservation")
def preserve_now(item: str) -> dict:
	"""Book form → Preserve Now (whatever the scope in Settings)."""
	frappe.only_for(MANAGERS)
	return preserve(item)


@frappe.whitelist()
@features.needs("preservation")
def check_now(item: str) -> dict:
	frappe.only_for(MANAGERS)
	return check(item)


@frappe.whitelist()
@features.needs("preservation")
def enqueue_preservation() -> int:
	frappe.only_for(MANAGERS)
	if not enabled():
		frappe.throw(_("Set a folder and what to preserve in Settings → Preservation first."))
	return queue_preservation(limit=0)


@frappe.whitelist()
@features.needs("preservation")
def second_copy_now(item: str) -> dict:
	"""Book form → Make Second Copy."""
	frappe.only_for(MANAGERS)
	return replicate(item)


@frappe.whitelist()
@features.needs("preservation")
def enqueue_second_copies() -> int:
	frappe.only_for(MANAGERS)
	if second() is None:
		frappe.throw(_("Set a second copy in Settings → Preservation first."))
	return queue_second(limit=0)


# -- serving a book from our copy ----------------------------------------------------------------


def copy_files(item_id: str) -> dict[str, str]:
	"""{name: path} of the newest version of our copy: the first copy, or the second when the first
	is gone and the second is a folder."""
	path = root()
	files = ocfl.head_files(path, item_id) if path else {}
	if not files:
		rep = second()
		if isinstance(rep, FolderReplica):
			files = ocfl.head_files(rep.root, item_id)
	return files


def copy_pdf(item_id: str) -> tuple[str, str] | None:
	"""(name, path) of the book's PDF in our copy: <id>.pdf when there is one, else the first PDF."""
	pdfs = {n: p for n, p in copy_files(item_id).items() if n.lower().endswith(".pdf")}
	if not pdfs:
		return None
	name = f"{item_id}.pdf" if f"{item_id}.pdf" in pdfs else sorted(pdfs)[0]
	return name, pdfs[name]


def start_serving(name: str, reason: str) -> bool:
	"""Keep a book on the portal from our copy (its PDF). False when we hold no PDF of it."""
	item_id = frappe.db.get_value("RD Item", name, "item_id")
	if not copy_pdf(item_id):
		return False
	doc = frappe.get_doc("RD Item", name)
	doc.served_from_copy = 1
	doc.published = 1
	doc.flags.ignore_permissions = True
	doc.save()  # the portal and its search see the change
	event(name, "Access from copy", "Success", reason)
	return True


@frappe.whitelist()
@features.needs("preservation")
def serve_from_copy(item: str, on: int = 1) -> dict:
	"""Book form → Serve From Our Copy / Stop Serving From Our Copy."""
	frappe.only_for(MANAGERS)
	if cint(on):
		if not start_serving(item, _("Served from our copy, by {0}").format(frappe.session.user)):
			frappe.throw(_("Our copy of this book has no PDF to serve."))
	else:
		doc = frappe.get_doc("RD Item", item)
		doc.served_from_copy = 0
		if doc.removed_from_source:
			doc.published = 0  # it isn't on archive.org either
		doc.flags.ignore_permissions = True
		doc.save()
		event(
			item,
			"Access from copy",
			"Success",
			_("No longer served from our copy, by {0}").format(frappe.session.user),
		)
	frappe.db.commit()
	return {"served_from_copy": cint(on)}


# -- BagIt exports -------------------------------------------------------------------------------


def exports_dir() -> str:
	path = root()
	if not path:
		frappe.throw(_("Set a folder in Settings → Preservation first."))
	return os.path.join(path, "exports")


def _bag_info(doc) -> dict:
	from sok_resdesk.catalogue import base_url, settings

	return {
		"Source-Organization": settings().get("portal_title") or "Research Desk",
		"Organization-Address": base_url(),
		"External-Identifier": doc.get("persistent_id") or doc.item_id,
		"External-Description": (doc.title or "")[:500],
		"Internal-Sender-Identifier": doc.item_id,
		"Bag-Software-Agent": agent(),
	}


def export_bags(names: list[str], label: str) -> dict:
	"""Bags of these books (their newest preserved version) in one zip in <first copy>/exports/."""
	from sok_resdesk.core import bagit

	books = []
	for name in names:
		doc = frappe.get_doc("RD Item", name)
		files = copy_files(doc.item_id)
		if files:
			books.append((doc.item_id, files, _bag_info(doc)))
	if not books:
		frappe.throw(_("None of these books has a preservation copy yet."))
	safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:80].strip("-") or "bags"
	file_name = f"{safe}-{now_datetime().strftime('%Y%m%d-%H%M%S')}.zip"
	out = os.path.join(exports_dir(), file_name)
	totals = bagit.write_bags(out, books)
	for item_id, _files, _info in books:
		event(item_id, "Export", "Success", _("BagIt: {0}").format(file_name))
	frappe.db.commit()
	return {**totals, "file": file_name}


@frappe.whitelist()
@features.needs("preservation")
def export_book(item: str) -> dict:
	"""Book form → Export BagIt: a bag of this book, ready to download."""
	frappe.only_for(MANAGERS)
	return export_bags([item], item)


@frappe.whitelist()
@features.needs("preservation")
def export_collection(collection: str) -> dict:
	"""Collection form → Export BagIt: bags of its preserved books, made in the background."""
	frappe.only_for(MANAGERS)
	names = frappe.get_all(
		"RD Item Collection", filters={"collection": collection, "parenttype": "RD Item"}, pluck="parent"
	)
	names = frappe.get_all(
		"RD Item", filters={"name": ("in", names or [""]), "preserved_on": ("is", "set")}, pluck="name"
	)
	if not names:
		frappe.throw(_("None of this collection's books has a preservation copy yet."))
	frappe.enqueue(
		"sok_resdesk.preservation.export_collection_job",
		queue="long",
		timeout=12 * 3600,
		names=names,
		label=collection,
		user=frappe.session.user,
	)
	return {"books": len(names)}


def export_collection_job(names: list[str], label: str, user: str) -> None:
	try:
		result = export_bags(names, label)
		subject = _("BagIt export ready: {0} ({1} books)").format(result["file"], result["bags"])
	except Exception as e:
		frappe.log_error(title=f"Research Desk: BagIt export of {label} failed")
		subject = _("BagIt export of {0} failed: {1}").format(label, str(e)[:200])
	try:
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": subject}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Research Desk: BagIt export notification not sent")
	frappe.db.commit()


@frappe.whitelist()
def exports() -> list[dict]:
	"""The bag files waiting in <first copy>/exports/, newest first."""
	frappe.only_for(MANAGERS)
	folder = exports_dir()
	if not os.path.isdir(folder):
		return []
	out = []
	for n in os.listdir(folder):
		if n.endswith(".zip"):
			st = os.stat(os.path.join(folder, n))
			out.append({"file": n, "bytes": st.st_size, "made": str(_dt_from(st.st_mtime))[:16]})
	return sorted(out, key=lambda r: r["made"], reverse=True)


def _dt_from(ts: float):
	import datetime

	return datetime.datetime.fromtimestamp(ts)


@frappe.whitelist(methods=["GET"])
def download_export(file: str):
	"""Stream a bag file to a manager (range requests work, so big files resume)."""
	frappe.only_for(MANAGERS)
	from werkzeug.utils import send_file

	if "/" in file or "\\" in file or not file.endswith(".zip"):
		raise frappe.PermissionError
	path = os.path.join(exports_dir(), file)
	if not os.path.isfile(path):
		raise frappe.DoesNotExistError
	return send_file(
		path, frappe.local.request.environ, conditional=True, as_attachment=True, download_name=file
	)


@features.scheduled("preservation")
def clean_exports(days: int = 14) -> int:
	"""Weekly: bag files older than `days` are removed (they can be made again any time)."""
	path = root()
	folder = os.path.join(path, "exports") if path else ""
	if not folder or not os.path.isdir(folder):
		return 0
	import time

	gone = 0
	for n in os.listdir(folder):
		p = os.path.join(folder, n)
		if os.path.isfile(p) and time.time() - os.path.getmtime(p) > days * 86400:
			os.remove(p)
			gone += 1
	return gone


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
	if second() is not None:
		seconds = dict(
			frappe.db.sql(
				"select second_copy_status, count(*) from `tabRD Item` where preserved_on is not null group by second_copy_status"
			)
		)
		bad += cint(seconds.get("Failed check")) + cint(seconds.get("Missing"))
		detail += " · " + _("second copy: {0}").format(f"{cint(seconds.get('Copied')):,}")
	return {
		"key": "preservation",
		"label": _("Preservation copies"),
		"state": "bad" if bad else "ok",
		"detail": detail + (" · " + _("{0} failed their check").format(bad) if bad else ""),
		"link": "/app/rd-preservation-event?outcome=Failure" if bad else "/app/rd-settings",
	}
