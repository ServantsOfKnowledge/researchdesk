"""Repository deposit: people give the library their own work, a reviewer accepts it.

A depositor (role *ResDesk Depositor*, or library staff on someone's behalf) makes a deposit on
the portal (/library/deposit) or in the Desk: the details, the licence, who may read the files
(and an embargo date), the files, and a declaration that they may share the work. They submit it;
a *different* person on the library staff reviews it and accepts it, asks for changes, or rejects
it. An accepted deposit becomes a book (an item folder under the deposit folder, so its PDF text,
OCR, downloads, access and preservation work as for any book in a folder), listed in the chosen
collection. An embargo keeps the files for logged-in readers until its date, then lifts itself.
"""

from __future__ import annotations

import os
import shutil

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, getdate, now_datetime, nowdate

from sok_resdesk import features
from sok_resdesk.core import deposit as core
from sok_resdesk.core import metaio

DT = "RD Deposit"
DEPOSITOR = "ResDesk Depositor"
STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
DEPOSITORS = (*STAFF, DEPOSITOR)
EDITABLE = ("Draft", "Needs Changes")  # a depositor can change a deposit only in these states


def max_mb() -> int:
	return cint(frappe.conf.get("resdesk_deposit_max_mb")) or core.DEFAULT_MAX_MB


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def _can_deposit() -> bool:
	return bool(_roles() & set(DEPOSITORS)) and frappe.session.user != "Guest"


def _is_staff() -> bool:
	return bool(_roles() & set(STAFF))


# -- document events ---------------------------------------------------------------------------------


def before_insert(doc) -> None:
	if not _can_deposit():
		frappe.throw(_("Depositing needs a depositor account: ask the library."), frappe.PermissionError)
	doc.depositor = doc.depositor if (_is_staff() and doc.depositor) else frappe.session.user
	doc.status = "Draft"


def validate(doc) -> None:
	doc.creators = "\n".join(core.lines(doc.creators))
	doc.subjects = "\n".join(core.lines(doc.subjects))
	doc.language = (doc.language or "").strip().lower()
	if doc.year and not 1000 <= cint(doc.year) <= getdate(nowdate()).year + 1:
		frappe.throw(_("The year is not a year."))
	if doc.embargo_until and doc.status in EDITABLE and getdate(doc.embargo_until) <= getdate(nowdate()):
		frappe.throw(_("The embargo has to end in the future. Leave it empty for none."))
	if not doc.is_new() and not doc.flags.by_deposit_api and not _is_staff() and doc.status not in EDITABLE:
		frappe.throw(_("This deposit is {0}: it can no longer be changed.").format(_(doc.status)))
	fill_files(doc)


def fill_files(doc) -> None:
	"""Name, format, size and SHA-256 of every attached file, taken on arrival; and what may not come in."""
	for row in doc.files or []:
		if row.sha256 or not row.file:
			continue
		path = file_path(row.file)
		if not path:
			frappe.throw(_("The file {0} could not be found.").format(row.file))
		row.file_name = os.path.basename(row.file)
		row.format = core.extension(row.file_name).lstrip(".").upper()
		row.size = os.path.getsize(path)
		problem = core.file_problem(row.file_name, row.size, max_mb())
		if problem:
			frappe.throw(problem)
		row.sha256 = core.sha256_of(path)


def file_path(file_url: str) -> str:
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return ""
	path = frappe.get_doc("File", name).get_full_path()
	return path if os.path.isfile(path) else ""


# -- the depositor's calls ---------------------------------------------------------------------------


def _mine(name: str):
	"""The deposit, if it is the caller's own (or the caller is staff)."""
	doc = frappe.get_doc(DT, name)
	if doc.depositor != frappe.session.user and not _is_staff():
		raise frappe.PermissionError
	return doc


@frappe.whitelist()
def options() -> dict:
	"""What the deposit form offers: licences, kinds of work, collections, limits."""
	frappe.only_for(DEPOSITORS)
	meta = frappe.get_meta(DT)
	return {
		"licences": [o for o in meta.get_field("licence").options.split("\n") if o],
		"kinds": [o for o in meta.get_field("item_type").options.split("\n") if o],
		"collections": frappe.get_all(
			"RD Collection", filters={"published": 1}, fields=["name", "title"], order_by="title"
		),
		"allowed": [e.lstrip(".") for e in core.ALLOWED],
		"max_mb": max_mb(),
		"fields": {
			f: frappe.get_meta(DT).get_field(f).description or ""
			for f in ("creators", "subjects", "embargo_until", "declaration", "language")
		},
	}


@frappe.whitelist()
def mine() -> list[dict]:
	"""My deposits, newest first."""
	frappe.only_for(DEPOSITORS)
	rows = frappe.get_all(
		DT,
		filters={"depositor": frappe.session.user},
		fields=[
			"name",
			"title",
			"status",
			"submitted_on",
			"review_notes",
			"item",
			"modified",
			"embargo_until",
		],
		order_by="modified desc",
		limit=200,
	)
	for r in rows:
		r.url = f"/library/item/{r.item}" if r.item and r.status == "Accepted" else ""
		r.ia_status = frappe.db.get_value("RD Item", r.item, "ia_sent_status") or "" if r.url else ""
	return rows


@frappe.whitelist()
def get(name: str) -> dict:
	frappe.only_for(DEPOSITORS)
	doc = _mine(name)
	out = doc.as_dict()
	out["files"] = [
		{"idx": r.idx, "file_name": r.file_name, "format": r.format, "size": r.size, "sha256": r.sha256}
		for r in doc.files
	]
	return out


FIELDS = (
	"title",
	"creators",
	"abstract",
	"subjects",
	"year",
	"language",
	"item_type",
	"collection",
	"licence",
	"access",
	"embargo_until",
	"declaration",
)


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def save(values, name: str = "") -> str:
	"""Make or change my draft. Returns the deposit's name."""
	frappe.only_for(DEPOSITORS)
	values = frappe.parse_json(values) if isinstance(values, str) else values
	if name:
		doc = _mine(name)
		if doc.status not in EDITABLE:
			frappe.throw(_("This deposit is {0}: it can no longer be changed.").format(_(doc.status)))
	else:
		doc = frappe.new_doc(DT)
	for f in FIELDS:
		if f in values:
			doc.set(f, values[f] or None if f in ("year", "embargo_until", "collection") else values[f])
	doc.flags.by_deposit_api = True
	doc.flags.ignore_permissions = True
	doc.save() if name else doc.insert()
	return doc.name


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def attach_file(name: str, file_url: str) -> dict:
	"""A file just uploaded (as a private file of this deposit) joins it."""
	frappe.only_for(DEPOSITORS)
	doc = _mine(name)
	if doc.status not in EDITABLE:
		frappe.throw(_("This deposit is {0}: it can no longer be changed.").format(_(doc.status)))
	doc.append("files", {"file": file_url})
	doc.flags.by_deposit_api = True
	doc.flags.ignore_permissions = True
	doc.save()
	row = doc.files[-1]
	return {"idx": row.idx, "file_name": row.file_name, "format": row.format, "size": row.size}


@frappe.whitelist(methods=["POST"])
def remove_file(name: str, idx: int) -> None:
	frappe.only_for(DEPOSITORS)
	doc = _mine(name)
	if doc.status not in EDITABLE:
		frappe.throw(_("This deposit is {0}: it can no longer be changed.").format(_(doc.status)))
	doc.files = [r for r in doc.files if r.idx != cint(idx)]
	for n, r in enumerate(doc.files, 1):
		r.idx = n
	doc.flags.by_deposit_api = True
	doc.flags.ignore_permissions = True
	doc.save()


def checks(doc) -> list[str]:
	"""Things a reviewer should know: files already deposited, works that read alike."""
	notes = []
	for row in doc.files:
		same = frappe.db.sql(
			"""select p.name from `tabRD Deposit File` f join `tabRD Deposit` p on p.name = f.parent
			where f.sha256 = %s and p.name != %s and p.status not in ('Rejected', 'Withdrawn') limit 1""",
			(row.sha256, doc.name),
		)
		if same:
			notes.append(_("{0} is the same file as one in {1}.").format(row.file_name, same[0][0]))
	first = (doc.title or "")[:20]
	if first:
		titles = frappe.get_all("RD Item", filters={"title": ("like", f"{first}%")}, pluck="title", limit=20)
		like = core.similar_title(doc.title, titles)
		if like:
			notes.append(_("The catalogue already has a book titled “{0}”.").format(like))
	return notes


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def submit(name: str) -> dict:
	"""Send my draft to the library's reviewers."""
	frappe.only_for(DEPOSITORS)
	doc = _mine(name)
	if doc.status not in EDITABLE:
		frappe.throw(_("This deposit is {0}.").format(_(doc.status)))
	missing = [
		label
		for label, ok in (
			(_("a title"), doc.title),
			(_("the authors"), doc.creators),
			(_("a licence"), doc.licence),
			(_("at least one file"), doc.files),
			(_("the declaration that you may deposit this work"), cint(doc.declaration)),
		)
		if not ok
	]
	if missing:
		frappe.throw(_("Before submitting, add: {0}.").format(", ".join(missing)))
	doc.warnings = "\n".join(checks(doc))
	doc.status = "Submitted"
	doc.submitted_on = now_datetime()
	doc.flags.by_deposit_api = True
	doc.flags.ignore_permissions = True
	doc.save()
	_tell(
		_reviewers(),
		_("New deposit to review: {0}").format(doc.title),
		_("{0} deposited “{1}”. Review it in the Desk: Research Desk → Deposits.").format(
			get_fullname(doc.depositor), doc.title
		),
	)
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def withdraw(name: str) -> dict:
	"""Take my deposit back (before it is accepted)."""
	frappe.only_for(DEPOSITORS)
	doc = _mine(name)
	if doc.status in ("Accepted", "Rejected", "Withdrawn"):
		frappe.throw(_("This deposit is {0}.").format(_(doc.status)))
	_set_status(doc, "Withdrawn")
	return {"status": doc.status}


def _set_status(doc, status: str, **values) -> None:
	doc.status = status
	for k, v in values.items():
		doc.set(k, v)
	doc.flags.by_deposit_api = True
	doc.flags.ignore_permissions = True
	doc.save()


# -- the reviewer's calls ----------------------------------------------------------------------------


def _reviewable(name: str):
	frappe.only_for(STAFF)
	doc = frappe.get_doc(DT, name)
	if doc.status != "Submitted":
		frappe.throw(_("This deposit is {0}, not waiting for review.").format(_(doc.status)))
	if doc.depositor == frappe.session.user and "System Manager" not in _roles():
		frappe.throw(_("Someone else has to review your own deposit."))
	return doc


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def request_changes(name: str, notes: str) -> dict:
	doc = _reviewable(name)
	if not (notes or "").strip():
		frappe.throw(_("Say what needs to change."))
	_set_status(
		doc, "Needs Changes", review_notes=notes, reviewer=frappe.session.user, decided_on=now_datetime()
	)
	_tell(
		[doc.depositor],
		_("Changes needed for your deposit: {0}").format(doc.title),
		_("The reviewer wrote: {0}\n\nChange the deposit and submit it again.").format(notes),
	)
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def reject(name: str, notes: str) -> dict:
	doc = _reviewable(name)
	if not (notes or "").strip():
		frappe.throw(_("Say why it is not accepted."))
	_set_status(doc, "Rejected", review_notes=notes, reviewer=frappe.session.user, decided_on=now_datetime())
	_tell(
		[doc.depositor],
		_("Your deposit was not accepted: {0}").format(doc.title),
		_("The reviewer wrote: {0}").format(notes),
	)
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
@features.needs("deposit")
def accept(name: str, notes: str = "", collection: str = "") -> dict:
	"""Accept: the work becomes a book, listed in the collection, readable as the depositor chose."""
	doc = _reviewable(name)
	item = publish(doc, collection or doc.collection)
	_set_status(
		doc,
		"Accepted",
		item=item,
		review_notes=notes,
		reviewer=frappe.session.user,
		decided_on=now_datetime(),
	)
	_tell(
		[doc.depositor],
		_("Your deposit is accepted: {0}").format(doc.title),
		_("It is in the library now: {0}/library/item/{1}").format(frappe.utils.get_url(), item),
	)
	return {"status": doc.status, "item": item}


def item_id_for(doc) -> str:
	return "dep-" + doc.name.split("-", 1)[-1].lower()


def publish(doc, collection: str = "") -> str:
	"""Write the work's item folder and catalogue it. Returns the book's identifier."""
	from sok_resdesk.local_source import deposits_root, ingest_local_one

	item_id = item_id_for(doc)
	root = deposits_root()
	folder = os.path.join(root, item_id)
	os.makedirs(folder, exist_ok=True)
	taken: set[str] = set()
	for row in doc.files:
		src = file_path(row.file)
		if not src:
			frappe.throw(_("The file {0} is missing.").format(row.file_name))
		shutil.copyfile(src, os.path.join(folder, core.safe_name(row.file_name, taken)))
	_verify_copies(doc, folder)
	record = {
		"item_id": item_id,
		"title": doc.title,
		"creators": core.lines(doc.creators),
		"year": cint(doc.year) or None,
		"language": doc.language,
		"subjects": core.lines(doc.subjects),
		"description": doc.abstract,
		"licence_url": core.LICENCE_URLS.get(doc.licence, ""),
		"rights": _("Deposited by {0}. Licence: {1}.").format(get_fullname(doc.depositor), doc.licence),
	}
	with open(os.path.join(folder, f"{item_id}_meta.xml"), "w", encoding="utf-8") as f:
		f.write(metaio.meta_xml(record, collections=[]))
	from sok_resdesk.core.deposit import DepositStore

	store = DepositStore(root)
	ingest_local_one(
		store, item_id, item_id, frappe._dict(name=None, check_archive_org=0), fetch_text=True, force=True
	)
	embargoed = bool(doc.embargo_until and getdate(doc.embargo_until) > getdate(nowdate()))
	book = frappe.get_doc("RD Item", item_id)
	book.item_type = doc.item_type or "Article"
	book.visibility = "Login to read" if embargoed else (doc.access or "Public")
	book.published = 1
	book.lock_metadata = 1  # a later ingest never undoes the reviewed details
	if collection and not any(r.collection == collection for r in book.get("curated_collections") or []):
		book.append("curated_collections", {"collection": collection})
	book.flags.ignore_permissions = True
	book.save()
	book.add_comment(
		"Info",
		_("Deposited by {0}, accepted by {1}.").format(
			get_fullname(doc.depositor), get_fullname(frappe.session.user)
		),
	)
	return item_id


def _verify_copies(doc, folder: str) -> None:
	"""The files in the book's folder are the ones deposited: their SHA-256 are checked."""
	want = {r.sha256 for r in doc.files}
	have = {
		core.sha256_of(os.path.join(folder, f))
		for f in os.listdir(folder)
		if core.extension(f) in core.ALLOWED
	}
	if want - have:
		frappe.throw(_("A file did not copy correctly: nothing was accepted. Try again."))


# -- embargo -----------------------------------------------------------------------------------------


@features.scheduled("deposit")
def release_embargoes() -> int:
	"""Daily: accepted deposits whose embargo has ended become readable as the depositor chose."""
	n = 0
	for name in frappe.get_all(
		DT,
		filters={
			"status": "Accepted",
			"embargo_lifted": 0,
			"embargo_until": ("<=", nowdate()),
			"item": ("is", "set"),
		},
		pluck="name",
	):
		doc = frappe.get_doc(DT, name)
		visibility = doc.access or "Public"
		frappe.db.set_value("RD Item", doc.item, "visibility", visibility)
		frappe.db.set_value(DT, name, "embargo_lifted", 1, update_modified=False)
		n += 1
	if n:
		frappe.db.commit()
	return n


# -- mail --------------------------------------------------------------------------------------------


def _reviewers() -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ("ResDesk Manager", "ResDesk Cataloguer")), "parenttype": "User"},
		pluck="parent",
	)
	return [
		u
		for u in dict.fromkeys(users)
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
	][:20]


def _tell(users: list[str], subject: str, message: str) -> None:
	"""Mail that must never stop the work it announces."""
	try:
		emails = [frappe.db.get_value("User", u, "email") for u in users]
		emails = [e for e in emails if e]
		if emails:
			frappe.sendmail(recipients=emails, subject=subject, message=message.replace("\n", "<br>"))
	except Exception:
		frappe.log_error(title="Research Desk: deposit mail not sent")
