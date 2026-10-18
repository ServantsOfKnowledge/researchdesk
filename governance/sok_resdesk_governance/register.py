"""The file register (docs/governance.md#file-register): a numbered file, its subject, level and department,
the records in it, who has it, and every movement from hand to hand.

A file follows the same need-to-know rules as a record: nobody sees, or is sent, a file above their
clearance. Who holds a file and where it has been is changed only by sending, receiving, closing and
reopening, never by editing the form, and every step is in the audit log.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cstr, getdate, now_datetime, nowdate

from sok_resdesk_governance import audit, clearance
from sok_resdesk_governance.classification import _may_classify
from sok_resdesk_governance.core import classification as levels

DT = "RD File"
OFFICERS = ("ResDesk Records Officer", "SOK Super Admin")
DESK = ("SOK Super Admin", "ResDesk Manager", "ResDesk Cataloguer", "ResDesk Records Officer")
KEPT = ("status", "held_by", "opened_on", "closed_on")  # changed only by the functions below


def number(doc) -> None:
	"""before_naming: the department's own number, or F-year-number."""
	given = (doc.file_number or "").strip()
	if given.upper().startswith("F-"):
		frappe.throw(_("Numbers starting F- are Research Desk's own: leave the number empty or use another."))
	doc.file_number = given or make_autoname("F-.YYYY.-.#####")


def _is_officer() -> bool:
	return frappe.session.user == "Administrator" or bool(set(frappe.get_roles()) & set(OFFICERS))


def _same(value) -> str:
	"""A form sends dates as text and the database as dates; empty is empty either way."""
	return cstr(value)[:19] if value else ""


def _rows(table) -> list[tuple]:
	return [
		(r.from_user or "", r.to_user or "", _same(r.sent_on), _same(r.received_on), r.remarks or "")
		for r in table or []
	]


def _parents() -> dict[str, str]:
	return dict(
		frappe.db.sql(
			"select name, parent_department from `tabRD Department` where ifnull(parent_department, '') != ''"
		)
	)


def _check_records(doc) -> None:
	"""A file is at least as restricted as what is in it, and nobody files what they cannot see."""
	inside = levels.expand([doc.department], _parents()) if doc.department else set()
	for r in doc.records or []:
		rank, department = clearance.scope_of(r.item)
		if not frappe.db.exists("RD Item", r.item) or not clearance.is_cleared(rank, department):
			frappe.throw(_("{0} is not a record you may file.").format(r.item))  # the same answer for both
		if rank > doc.class_rank or (department and department not in inside):
			frappe.throw(
				_(
					"{0} is {1} of {2}: the file must be at least as restricted, in the same office or above."
				).format(r.item, levels.LEVELS[rank], department or _("no department"))
			)


def files_below(items: list[str], rank: int, department: str | None) -> int:
	"""How many files hold one of `items` while less restricted than a record of this level and department
	would need (the file must be at least as restricted, in the same office or above)."""
	if not items:
		return 0
	parents = _parents()
	below = 0
	for f in frappe.db.sql(
		"""select distinct f.name, f.class_rank, f.department from `tabRD File Record` r
		join `tabRD File` f on f.name = r.parent where r.item in %s""",
		(tuple(items),),
		as_dict=True,
	):
		inside = levels.expand([f.department], parents) if f.department else set()
		if rank > (f.class_rank or 0) or (department and department not in inside):
			below += 1
	return below


def on_validate(doc, method=None) -> None:
	doc.class_rank = levels.rank(doc.classification)
	if doc.department and not frappe.db.exists("RD Department", doc.department):
		frappe.throw(_("Unknown department: {0}").format(doc.department))
	old = doc.get_doc_before_save()
	if old is None:
		if doc.class_rank or doc.department:  # an ordinary file needs no classifier
			_may_classify(doc.classification, doc.department)
		doc.status, doc.opened_on, doc.closed_on = "Open", nowdate(), None
		doc.held_by, doc.movements = frappe.session.user, []
		_check_records(doc)
		return
	if doc.flags.rd_register:
		return
	if any(_same(doc.get(f)) != _same(old.get(f)) for f in KEPT) or _rows(doc.movements) != _rows(
		old.movements
	):
		frappe.throw(
			_("Who has a file, and where it has been, change only by sending, receiving or closing it.")
		)
	if not (_is_officer() or old.held_by == frappe.session.user):
		frappe.throw(_("Only the person who has the file, or a records officer, can change it."))
	if old.status == "Closed":
		frappe.throw(_("Reopen a closed file to change it."))
	if (old.classification, old.department) != (doc.classification, doc.department):
		for level, department in ((old.classification, old.department), (doc.classification, doc.department)):
			if levels.rank(level) or department:
				_may_classify(level, department)
	_check_records(doc)


def on_update(doc, method=None) -> None:
	if doc.get_doc_before_save() is None:
		audit.record("file", doc.name, f"opened: {doc.classification} {doc.department or ''}".strip())


def _locked(file: str):
	"""The file, under a row lock so two clerks cannot both act on it, if the person may see it."""
	frappe.db.sql(f"select name from `tab{DT}` where name=%s for update", file)
	doc = frappe.get_doc(DT, file)
	doc.check_permission("read")
	doc.flags.rd_register = True  # on this document only, and gone with it
	return doc


def _pending(doc):
	last = (doc.movements or [None])[-1]
	return last if last and not last.received_on else None


def _holder_or_officer(doc) -> None:
	if not (_is_officer() or doc.held_by == frappe.session.user):
		frappe.throw(
			_("Only the person who has the file, or a records officer, can do that."), frappe.PermissionError
		)


@frappe.whitelist(methods=["POST"])
def send(file: str, to_user: str, remarks: str = "") -> None:
	"""Pass the file to someone who is cleared for it; it stays with the sender until they receive it."""
	doc = _locked(file)
	_holder_or_officer(doc)
	if doc.status != "Open":
		frappe.throw(_("A closed file cannot be sent."))
	if _pending(doc):
		frappe.throw(_("The file is still waiting to be received."))
	# one answer whether the person is not a user, cannot receive files, or is not cleared for it
	ok = bool(frappe.db.get_value("User", to_user, "enabled")) and bool(
		set(frappe.get_roles(to_user)) & set(DESK)
	)
	ok = ok and clearance.is_cleared(doc.class_rank, doc.department, to_user)
	for r in doc.records or []:  # and for what is in it
		ok = ok and clearance.is_cleared(*clearance.scope_of(r.item), to_user)
	if not ok:
		frappe.throw(_("{0} cannot receive this file.").format(to_user))
	doc.append(
		"movements",
		{
			"from_user": frappe.session.user,
			"to_user": to_user,
			"sent_on": now_datetime(),
			"remarks": (remarks or "")[:500],
		},
	)
	doc.save(ignore_permissions=True)
	audit.record("file", file, f"sent to {to_user}")


@frappe.whitelist(methods=["POST"])
def receive(file: str) -> None:
	doc = _locked(file)
	move = _pending(doc)
	if not move or move.to_user != frappe.session.user:
		frappe.throw(_("There is nothing sent to you to receive."), frappe.PermissionError)
	move.received_on, doc.held_by = now_datetime(), frappe.session.user
	doc.save(ignore_permissions=True)
	audit.record("file", file, "received")


@frappe.whitelist(methods=["POST"])
def close(file: str) -> None:
	doc = _locked(file)
	_holder_or_officer(doc)
	if doc.status != "Open" or _pending(doc):
		frappe.throw(_("Only an open file that is not on its way can be closed."))
	doc.status, doc.closed_on = "Closed", getdate(nowdate())
	doc.save(ignore_permissions=True)
	audit.record("file", file, "closed")


@frappe.whitelist(methods=["POST"])
def reopen(file: str) -> None:
	doc = _locked(file)
	if not _is_officer():
		frappe.throw(_("Only a records officer can reopen a file."), frappe.PermissionError)
	if doc.status != "Closed":
		frappe.throw(_("The file is not closed."))
	doc.status, doc.closed_on = "Open", None
	doc.save(ignore_permissions=True)
	audit.record("file", file, "reopened")
