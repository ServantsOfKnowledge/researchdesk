"""Disclosure requests and redaction (docs/governance.md#disclosure-requests-and-redaction).

A request names the records asked for. The records officer decides each: disclose, disclose with parts
covered, or withhold, with the ground relied on. Only then is a package made: the whole file, a picture
of each page with the covered parts burned in (nothing under a box survives), or nothing, and a reply
that lists every decision. The package is a private file on the request, with its checksum.
"""

from __future__ import annotations

import base64
import hashlib
import io
import zipfile

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, cstr, getdate, now_datetime, nowdate

from sok_resdesk.core.pdfrender import RenderError, page_count, poppler, render
from sok_resdesk_governance import audit, clearance
from sok_resdesk_governance.core import disclosure as rules
from sok_resdesk_governance.core.redact import MAX_SIDE, burn, pdf_of

DT = "RD Disclosure Request"
OFFICERS = ("ResDesk Records Officer", "SOK Super Admin")
KEPT = ("status", "due_on", "decided_by", "decided_on", "released_on", "release_file", "release_hash")
DPI = 200  # a readable page that stays a reasonable size
DRAW_DPI = 100  # the page boxes are drawn on, on screen
MAX_PAGES = 400  # redacted pages in one package: each is drawn, burned and encoded on its own
MAX_BYTES = 200 * 1024 * 1024
STALE_HOURS = 2  # a package still "Preparing" after this long died with its worker: release again


def _only_officers() -> None:
	if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & set(OFFICERS):
		frappe.throw(_("Only the records officer may do this."), frappe.PermissionError)


def _lock(name: str, *allowed: str) -> None:
	"""Under a row lock, so two clicks cannot both win."""
	row = frappe.db.sql(f"select status from `tab{DT}` where name = %s for update", name)
	if not row or row[0][0] not in allowed:
		frappe.db.rollback()
		frappe.throw(_("This request is not in a state for that."))


def _rows(table, fields) -> list[tuple]:
	return [tuple(cstr(r.get(f)) for f in fields) for r in table or []]


def _may_see(item: str) -> bool:
	rank, department = clearance.scope_of(item)
	return bool(frappe.db.exists("RD Item", item)) and clearance.is_cleared(rank, department)


def on_validate(doc) -> None:
	_only_officers()
	records = ("item", "decision", "ground")
	boxes = ("item", "page", "left", "top", "width", "height", "reason")
	for r in list(doc.records or []) + list(doc.redactions or []):
		if not _may_see(r.item):  # the same answer for a record that is missing and one that is not theirs
			frappe.throw(_("{0} is not a record you may include.").format(r.item))
	if doc.is_new():
		doc.status = "Received"
		doc.due_on = rules.due_on(
			getdate(doc.received_on or nowdate()),
			cint(frappe.db.get_single_value("RD Settings", "disclosure_days")) or 30,
		)
		for f in KEPT[2:]:
			doc.set(f, None)
		for r in doc.records or []:
			r.file_sha256 = r.scope_seen = None
	else:
		old = doc.get_doc_before_save()
		taken = {r.name: r for r in old.records or []}
		for r in doc.records or []:  # what was seen at the decision is not for editing
			was = taken.get(r.name)
			r.file_sha256, r.scope_seen = (was.file_sha256, was.scope_seen) if was else (None, None)
		if old.status in ("Preparing", "Released", "Closed"):
			frappe.throw(_("A request that is {0} cannot be changed.").format(old.status.lower()))
		for f in KEPT:  # these change only through the buttons
			doc.set(f, old.get(f))
		changed = (
			_rows(doc.records, records) != _rows(old.records, records)
			or _rows(doc.redactions, boxes) != _rows(old.redactions, boxes)
			or cstr(doc.decision_note) != cstr(old.decision_note)
		)
		if old.status == "Decided" and changed:  # a decision stands only as it was made
			doc.status, doc.decided_by, doc.decided_on = "In review", None, None
	if doc.records and doc.status == "Received":
		doc.status = "In review"


def _state(item: str) -> tuple[str, str]:
	"""(SHA-256 of the record's PDF or "", its level and department)."""
	from sok_resdesk.pdfs import pdf_path

	path = pdf_path(item)
	sha = hashlib.sha256()
	if path:
		with open(path, "rb") as f:
			for chunk in iter(lambda: f.read(1 << 20), b""):
				sha.update(chunk)
	rank, department = clearance.scope_of(item)
	return (sha.hexdigest() if path else "", f"{rank}:{department}")


def _check_pages(doc) -> None:
	"""A box on a page the record does not have would cover nothing: that is refused, not skipped."""
	from sok_resdesk.pdfs import pdf_path

	counts = {}
	for item in {r.item for r in doc.redactions or []}:
		path = pdf_path(item)
		if not path:
			frappe.throw(_("{0} has no file to cover parts of.").format(item))
		counts[item] = page_count(path)
	boxes = [{"item": r.item, "page": r.page} for r in doc.redactions or []]
	found = rules.pages_off(boxes, counts)
	if found:
		frappe.throw("<br>".join(found[:8]))


def _lines(doc) -> list[str]:
	boxes = [
		{f: r.get(f) for f in ("item", "page", "left", "top", "width", "height")}
		for r in doc.redactions or []
	]
	records = [{f: r.get(f) for f in ("item", "decision", "ground")} for r in doc.records or []]
	return rules.problems(records, boxes)


@frappe.whitelist(methods=["POST"])
def decide(name: str) -> None:
	"""The records officer's decision: from now on the records and boxes cannot be changed without
	deciding again."""
	_only_officers()
	_lock(name, "In review")
	doc = frappe.get_doc(DT, name)
	doc.check_permission("write")
	if not doc.records:
		frappe.throw(_("Only a request in review, with records, can be decided."))
	found = _lines(doc)
	if found:
		frappe.throw("<br>".join(found[:8]))
	_check_pages(doc)
	for r in doc.records:  # what was decided on: a later change to the file or its level stops the package
		sha, scope = _state(r.item)
		frappe.db.set_value("RD Disclosure Record", r.name, {"file_sha256": sha, "scope_seen": scope})
	now = now_datetime()
	frappe.db.set_value(DT, name, {"status": "Decided", "decided_by": frappe.session.user, "decided_on": now})
	audit.record(
		"disclosure_decided",
		detail=f"{name}: " + ", ".join(f"{r.item} {r.decision}" for r in doc.records[:40]),
	)


@frappe.whitelist(methods=["POST"])
def release(name: str) -> None:
	"""Makes the package in the background."""
	_only_officers()
	row = frappe.db.get_value(DT, name, ["status", "modified"])
	if row and row[0] == "Preparing" and row[1] < add_to_date(None, hours=-STALE_HOURS):
		frappe.db.set_value(DT, name, "status", "Decided")
	_lock(name, "Decided")
	frappe.get_doc(DT, name).check_permission("write")
	frappe.db.set_value(DT, name, {"status": "Preparing", "release_error": None})
	frappe.enqueue(
		"sok_resdesk_governance.disclosure.build",
		queue="long",
		timeout=4 * 3600,
		name=name,
		user=frappe.session.user,
		enqueue_after_commit=True,
	)
	audit.record("disclosure_release_started", detail=name)


@frappe.whitelist(methods=["POST"])
def close(name: str, reason: str = "") -> None:
	"""Withdrawn, refused whole, or finished: the request stays as the record of what was asked."""
	_only_officers()
	_lock(name, "Received", "In review", "Decided", "Released")
	frappe.get_doc(DT, name).check_permission("write")
	frappe.db.set_value(DT, name, {"status": "Closed", "closed_note": (reason or "")[:500]})
	audit.record("disclosure_closed", detail=f"{name}: {(reason or '')[:200]}")


def _page_of_request(name: str, item: str, leaf: int):
	"""The request, when this officer may look at that page of that record of it."""
	_only_officers()
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	if leaf < 1 or item not in {r.item for r in doc.records}:
		frappe.throw(_("Not a page of a record on this request."))
	if not _may_see(item):  # an officer sees only what their own clearance shows
		frappe.throw(_("You are not cleared for this record."), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["POST"])
def page_image(name: str, item: str, leaf: int) -> dict:
	"""One page of a record as it is, for drawing the boxes on: a data URL and the record's page count."""
	from sok_resdesk.pdfs import pdf_path

	leaf = cint(leaf)
	_page_of_request(name, item, leaf)
	path = pdf_path(item)
	if not path:
		frappe.throw(_("{0} has no file to cover parts of.").format(item))
	pages = page_count(path)
	if leaf > pages:
		frappe.throw(_("{0} has {1} pages.").format(item, pages))
	if not poppler():
		frappe.throw(_("Redaction needs poppler-utils (pdftoppm) on the server."))
	_not_huge(path, leaf - 1, DRAW_DPI, 4000)  # a page to draw on, not to print
	png = render(path, leaf - 1, DRAW_DPI, grey=False, fmt="png")
	audit.record("disclosure_page_shown", item, f"{name} page {leaf}")
	return {"image": "data:image/png;base64," + base64.b64encode(png).decode(), "pages": pages}


@frappe.whitelist(methods=["POST"])
def preview(name: str, item: str, leaf: int) -> str:
	"""One page of a record as it would be released, as a data URL, for checking the boxes."""
	leaf = cint(leaf)
	doc = _page_of_request(name, item, leaf)
	audit.record("disclosure_preview", item, f"{name} page {leaf}")
	return "data:image/png;base64," + base64.b64encode(_page(doc, item, leaf, preview=True)).decode()


def _page(doc, item: str, leaf: int, preview: bool = False) -> bytes:
	from sok_resdesk.pdfs import pdf_path

	path = pdf_path(item)
	if not path:
		raise RenderError(_("{0} has no file to show.").format(item))
	if not poppler():  # without it a page is not drawn whole, and a covered page must be
		raise RenderError(_("Redaction needs poppler-utils (pdftoppm) on the server."))
	boxes = [r for r in doc.redactions if r.item == item and cint(r.page) == leaf]
	if boxes:
		_not_huge(path, leaf - 1, 72 if preview else DPI)
	ground = next((r.ground for r in doc.records if r.item == item), "")  # the one told to the applicant
	return burn(
		render(path, leaf - 1, 72 if preview else DPI, grey=False, fmt="png"),
		[r.as_dict() for r in boxes],
		label=ground or "" if not preview else "",
	)


def _not_huge(path: str, index: int, dpi: int, limit: int = MAX_SIDE) -> None:
	"""A page whose drawing would be enormous (a huge MediaBox) is refused before it is drawn."""
	from pypdf import PdfReader

	try:
		box = PdfReader(path).pages[index].mediabox
		side = max(float(box.width), float(box.height)) / 72 * dpi
	except Exception as e:  # a damaged file is a refusal, not a server error
		raise RenderError(_("This file could not be read.")) from e
	if side > limit:
		raise RenderError(_("A page is too large to redact."))


def _catalogue(item: str) -> str:
	title, year = frappe.db.get_value("RD Item", item, ["title", "year"]) or (item, None)
	return f"{item}: {title}" + (f" ({year})" if year else "")


def build(name: str, user: str) -> None:
	"""Background: the package, from the decisions as they stand now, by someone cleared for every record."""
	frappe.set_user(user)
	try:
		_build(name)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Research Desk: the package for {name} could not be made")
		frappe.db.set_value(DT, name, {"status": "Decided", "release_error": cstr(e)[:500]})
	frappe.db.commit()


def _build(name: str) -> None:
	import os
	import tempfile

	from sok_resdesk.pdfs import pdf_path

	_only_officers()  # the person who asked may have lost the role since
	doc = frappe.get_doc(DT, name)
	found = _lines(doc)  # the request may have changed since it was decided: say so rather than release
	if found:
		raise ValueError("; ".join(found[:5]))
	_check_pages(doc)
	for r in doc.records:
		if not _may_see(r.item):
			raise ValueError(_("{0} is not a record you may release.").format(r.item))
		if not r.scope_seen or (r.file_sha256 or "", r.scope_seen) != _state(r.item):
			# the file or the level changed since the decision: the boxes may sit on the wrong place
			frappe.db.set_value(DT, name, "status", "In review")
			raise ValueError(_("{0} has changed since it was decided: decide again.").format(r.item))
	appeal = cstr(frappe.db.get_single_value("RD Settings", "disclosure_appeal_note"))
	out, total, pages = io.BytesIO(), 0, 0
	index = [
		f"Reply to {doc.name}",
		f"Applicant: {doc.applicant}",
		f"Received: {doc.received_on}   Decided: {cstr(doc.decided_on)[:10]}",
		"",
		f"Asked for: {doc.subject}",
		"",
	]
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as tmp:
		for r in doc.records:
			if r.decision == rules.WITHHOLD:  # not even its title: that may be what is withheld
				index.append(f"- {r.item}: {r.decision}. Ground: {r.ground}")
				continue
			line = f"- {_catalogue(r.item)}: {r.decision}"
			if r.decision != rules.DISCLOSE:
				line += f". Ground: {r.ground}"
			path = pdf_path(r.item)
			if not path:
				index.append(line + ". (No file held: the entry above is all there is.)")
				continue
			if r.decision == rules.DISCLOSE:
				total += os.path.getsize(path)
				if total > MAX_BYTES:
					raise ValueError("The package is too large: split the request.")
				z.write(path, f"{r.item}.pdf")
				index.append(line)
				continue
			n = page_count(path)
			pages += n
			if pages > MAX_PAGES:
				raise ValueError("Too many pages for one package: split the request.")
			files = []
			for leaf in range(1, n + 1):  # one page in memory at a time; the rest wait on disk
				files.append(os.path.join(tmp, f"{len(files)}.png"))
				with open(files[-1], "wb") as f:
					f.write(_page(doc, r.item, leaf))
			data = pdf_of(files, DPI)
			for f in files:
				os.remove(f)
			total += len(data)
			if total > MAX_BYTES:
				raise ValueError("The package is too large: split the request.")
			z.writestr(f"{r.item}-redacted.pdf", data)
			index.append(line + f". {sum(1 for b in doc.redactions if b.item == r.item)} parts covered.")
		if doc.decision_note:
			index += ["", "Reasons:", doc.decision_note]
		if appeal:
			index += ["", "Appeal:", appeal]
		z.writestr("reply.txt", "\n".join(index) + "\n")
	data = out.getvalue()
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}.zip",
			"attached_to_doctype": DT,
			"attached_to_name": name,
			"attached_to_field": "release_file",
			"is_private": 1,
			"content": data,
		}
	).insert(ignore_permissions=True)
	digest = hashlib.sha256(data).hexdigest()
	frappe.db.set_value(
		DT,
		name,
		{
			"status": "Released",
			"released_on": now_datetime(),
			"release_file": file.file_url,
			"release_hash": digest,
			"release_error": None,
		},
	)
	audit.record(
		"disclosure_released",
		detail=f"{name}: {len(doc.records)} records, {pages} pages redacted, sha256 {digest}",
	)
