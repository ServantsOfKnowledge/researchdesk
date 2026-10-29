"""Interlibrary loan: a member asks the library for a book it does not have; staff ask another library, receive
the book, lend it to the member, and send it back. The other way round, another library asks for one of ours.

The steps (core/ill.py) are fixed, so a book cannot reach the member before it has arrived. A fee charged by
the other library becomes a fine on the member, which they pay like any other. No email is sent: the member
sees the request and its step on My library.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, nowdate

from sok_resdesk import features, lending
from sok_resdesk.core import ill as rules
from sok_resdesk.core import lending as lrules
from sok_resdesk.lending import STAFF

DEFAULT_MAX_OPEN = 3


def _staff() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for(STAFF)


def _note(doc, text: str) -> None:
	line = f"{now_datetime():%Y-%m-%d %H:%M} {frappe.session.user}: {text}"
	doc.notes = f"{doc.notes}\n{line}".strip() if doc.notes else line


@frappe.whitelist()
def steps(request: str) -> list[str]:
	"""The steps a request may take next (for the buttons on its form)."""
	_staff()
	doc = frappe.db.get_value("RD ILL Request", request, ["direction", "status"], as_dict=True)
	return list(rules.allowed(doc.direction, doc.status)) if doc else []


@frappe.whitelist(methods=["POST"])
def advance(request: str, to: str, note: str = "") -> dict:
	"""Move a request to its next step (only the steps core/ill.py allows)."""
	_staff()
	doc = frappe.get_doc("RD ILL Request", request)
	if not rules.can_move(doc.direction, doc.status, to):
		frappe.throw(_("A request that is {0} cannot go to {1}.").format(_(doc.status), _(to)))
	if doc.direction == "Borrowing":
		_borrowing_step(doc, to)
	else:
		_lending_step(doc, to)
	_note(doc, f"{doc.status} → {to}" + (f": {note}" if note else ""))
	doc.status = to
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status, "message": _("Now {0}.").format(_(to))}


def _borrowing_step(doc, to: str) -> None:
	if to == "Sent" and not (doc.partner_library or "").strip():
		frappe.throw(_("Say which library the request goes to."))
	if to == "Lent to Patron":
		patron = lending._patron(doc.patron)
		why = lending._standing(patron)
		if why:
			lending.refuse(why)
		cat = lending._category(patron.category)
		doc.due_on = lrules.due_date(getdate(nowdate()), cat.loan_days, lending._closed())


def _lending_step(doc, to: str) -> None:
	if to == "Approved" and doc.copy:
		if frappe.db.get_value("RD Copy", doc.copy, "status") != "Available":
			frappe.throw(_("The copy is not on the shelf."))
	if to == "Sent":
		if not doc.copy:
			frappe.throw(_("Choose the copy that goes."))
		if frappe.db.get_value("RD Copy", doc.copy, "status") != "Available":
			frappe.throw(_("The copy is not on the shelf."))
		frappe.db.set_value("RD Copy", doc.copy, "status", "Interlibrary loan")
	if to == "Returned" and doc.copy:
		lending._release_copy(doc.copy, frappe.db.get_value("RD Copy", doc.copy, "item"))


@frappe.whitelist(methods=["POST"])
def charge_fee(request: str) -> dict:
	"""Charge the other library's fee (or postage) to the member as a fine, once."""
	_staff()
	frappe.db.get_value("RD ILL Request", request, "name", for_update=True)  # two clicks charge once
	doc = frappe.get_doc("RD ILL Request", request)
	if doc.direction != "Borrowing" or not doc.patron:
		frappe.throw(_("Only a borrowing request has a member to charge."))
	if doc.fee_charged:
		frappe.throw(_("The fee is already charged."))
	if not (doc.fee and doc.fee > 0):
		frappe.throw(_("There is no fee to charge."))
	frappe.get_doc(
		{
			"doctype": "RD Fine",
			"patron": doc.patron,
			"reason": "Fee",
			"amount": doc.fee,
			"status": "Due",
			"note": _("Interlibrary loan {0}").format(doc.name),
		}
	).insert(ignore_permissions=True)
	doc.fee_charged = 1
	doc.flags.ignore_permissions = True
	doc.save()
	return {"message": _("Fee charged to the member.")}


# -- the member --------------------------------------------------------------------------------------


def mine(patron: str) -> list[dict]:
	"""A member's interlibrary requests that are not closed, for My library."""
	rows = frappe.get_all(
		"RD ILL Request",
		filters={"patron": patron, "direction": "Borrowing", "status": ("not in", rules.CLOSED)},
		fields=["name", "title", "author", "status", "due_on"],
		order_by="creation desc",
	)
	return [{**r, "due_on": str(r.due_on or "")} for r in rows]


@frappe.whitelist(methods=["POST"])
def request_mine(title: str, author: str = "", isbn: str = "", notes: str = "") -> dict:
	"""A member asks for a book the library does not have."""
	member = lending._me()
	title = (title or "").strip()[:300]
	if not title:
		frappe.throw(_("Please give the title of the book."))
	limit = cint(frappe.db.get_single_value("RD Settings", "lending_ill_max") or DEFAULT_MAX_OPEN)
	if limit and len(mine(member.name)) >= limit:
		frappe.throw(_("You have {0} requests open already. Please wait until one is done.").format(limit))
	doc = frappe.get_doc(
		{
			"doctype": "RD ILL Request",
			"direction": "Borrowing",
			"status": "Requested",
			"patron": member.name,
			"title": title,
			"author": (author or "").strip()[:200],
			"isbn": (isbn or "").strip()[:40],
			"notes": (notes or "").strip()[:500],
		}
	)
	doc.insert(ignore_permissions=True)
	return {
		"request": doc.name,
		"message": _("Your request is with the library. We will tell you here when the book comes."),
	}


@frappe.whitelist(methods=["POST"])
def cancel_mine(request: str) -> dict:
	member = lending._me()
	row = frappe.db.get_value("RD ILL Request", request, ["patron", "status", "direction"], as_dict=True)
	if not row or row.patron != member.name or row.direction != "Borrowing":
		frappe.throw(_("That is not your open request."), frappe.PermissionError)
	if row.status != "Requested":
		frappe.throw(_("The library has already started on this request. Please ask at the desk."))
	frappe.db.set_value("RD ILL Request", request, "status", "Cancelled")
	return {"message": _("Request cancelled.")}
