"""Approval to read: a book set to *Approval to read* is found and cited by anyone, but read only by staff
and by readers a librarian has approved for that book (an RD Access Request, optionally ending on a date).

A reader asks from the book's page; staff (managers and cataloguers, the library's librarians) approve or
decline in the Desk. Reading itself is decided in access.py (effective / can_read), which fails closed:
a book needing approval is unreadable unless a live approval or a staff role says otherwise.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from sok_resdesk import access
from sok_resdesk.core import access as rules
from sok_resdesk.ratelimit import rate_limit

DOCTYPE = "RD Access Request"


def _book(item_id: str):
	row = frappe.db.get_value("RD Item", item_id, ["published", "visibility", "title"], as_dict=True)
	if not row or not row.published or row.visibility != rules.APPROVAL:
		frappe.throw(_("This book does not need approval."), frappe.DoesNotExistError)
	return row


def _live(doc) -> bool:
	return doc.status == "Approved" and (
		not doc.valid_until or getdate(doc.valid_until) >= getdate(nowdate())
	)


def state(item_id: str, user: str | None = None) -> dict:
	"""What the book's page tells this reader: {"status": "", "Pending", "Approved", "Declined", "Expired",
	"note", "valid_until"}; "" when they have not asked."""
	user = user or frappe.session.user
	if user == "Guest":
		return {"status": ""}
	row = frappe.db.get_value(
		DOCTYPE, {"item": item_id, "user": user}, ["status", "note", "valid_until"], as_dict=True
	)
	if not row:
		return {"status": ""}
	status = "Expired" if row.status == "Approved" and not _live(row) else row.status
	return {"status": status, "note": row.note or "", "valid_until": str(row.valid_until or "")}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=3600)
def request(item_id: str, reason: str = "") -> dict:
	"""A reader asks to read a book that needs approval."""
	user = frappe.session.user
	if user == "Guest" or not access.is_member(user):
		frappe.throw(_("Log in as a reader to ask for access."), frappe.PermissionError)
	book = _book(item_id)
	reason = (reason or "").strip()[:1000]
	name = frappe.db.get_value(DOCTYPE, {"item": item_id, "user": user})
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if _live(doc):
			return {"status": "Approved"}
		if doc.status == "Pending":
			doc.reason = reason or doc.reason
			doc.save(ignore_permissions=True)
			return {"status": "Pending"}
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.item, doc.user = item_id, user
	doc.status, doc.reason, doc.requested_on, doc.note = "Pending", reason, now_datetime(), ""
	doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
	access.notify_managers(
		doc,
		_("{0} asked to read {1}").format(frappe.db.get_value("User", user, "full_name") or user, book.title),
		roles=access.STAFF_ROLES,
	)
	return {"status": "Pending"}


@frappe.whitelist(methods=["POST"])
def withdraw(item_id: str) -> dict:
	"""A reader takes their request back."""
	user = frappe.session.user
	name = frappe.db.get_value(DOCTYPE, {"item": item_id, "user": user, "status": "Pending"})
	if name:
		frappe.db.set_value(DOCTYPE, name, "status", "Withdrawn")
	return {"status": "Withdrawn" if name else state(item_id)["status"]}


@frappe.whitelist(methods=["POST"])
def decide(names, status: str, valid_until: str | None = None, note: str = "") -> dict:
	"""Approve or decline requests (librarians: managers and cataloguers)."""
	if not access.is_staff():
		frappe.throw(_("Only the library's staff can decide on requests."), frappe.PermissionError)
	if status not in ("Approved", "Declined"):
		frappe.throw(_("Choose Approved or Declined."))
	names = frappe.parse_json(names) if isinstance(names, str) else names
	done = 0
	for name in names or []:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.status == status and status == "Declined":
			continue
		doc.status = status
		if valid_until:
			doc.valid_until = valid_until
		if note:
			doc.note = note[:1000]
		doc.save(ignore_permissions=True)
		done += 1
	return {"count": done, "message": _("{0} requests marked {1}.").format(done, _(status))}


def tell_reader(doc) -> None:
	"""An email to the reader about the decision (the book's page shows it too, if email is not set up)."""
	from sok_resdesk.catalogue import base_url, portal_title

	email = frappe.db.get_value("User", doc.user, "email")
	title = frappe.db.get_value("RD Item", doc.item, "title") or doc.item
	link = f"{base_url()}/library/item/{doc.item}"
	if doc.status == "Approved":
		until = _(" until {0}").format(doc.valid_until) if doc.valid_until else ""
		subject = _("You can read {0}").format(title)
		body = _("The library approved your request to read {0}{1}. Open it at {2}").format(
			title, until, link
		)
	else:
		subject = _("Your request to read {0}").format(title)
		body = _("The library could not approve your request to read {0}. {1}").format(title, doc.note or "")
	try:
		frappe.sendmail(
			recipients=[email], subject=f"{portal_title()}: {subject}", message=body, delayed=True
		)
	except Exception:
		pass  # email may not be set up; the book's page shows the decision
