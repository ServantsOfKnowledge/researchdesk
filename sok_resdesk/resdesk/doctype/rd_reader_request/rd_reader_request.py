# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from sok_resdesk.access import READER_ROLE, notify_managers


class RDReaderRequest(Document):
	def validate(self):
		if self.user and not self.email:
			self.email = frappe.db.get_value("User", self.user, "email")
		if self.user and not self.full_name:
			self.full_name = frappe.db.get_value("User", self.user, "full_name")
		if self.has_value_changed("status") and not self.is_new():
			self.decided_by = frappe.session.user
			self.decided_on = now_datetime()

	def after_insert(self):
		if self.status == "Pending":
			notify_managers(self)

	def on_update(self):
		if not self.has_value_changed("status") and not self.flags.in_insert:
			return
		user = frappe.get_doc("User", self.user)
		user.flags.ignore_permissions = True
		has = READER_ROLE in {r.role for r in user.roles}
		if self.status == "Approved" and not has:
			user.add_roles(READER_ROLE)
			_tell(user, approved=True)
		elif self.status != "Approved" and has:
			user.remove_roles(READER_ROLE)
		elif self.status == "Rejected":
			_tell(user, approved=False)


def _tell(user, approved: bool):
	from sok_resdesk.catalogue import base_url, portal_title

	if approved:
		subject = frappe._("Your {0} account is ready").format(portal_title())
		body = frappe._("You can now read every book on {0}. Log in at {1}").format(
			portal_title(), f"{base_url()}/login"
		)
	else:
		subject = frappe._("Your {0} account request").format(portal_title())
		body = frappe._(
			"The library could not approve your reader account. Reply to this email if you have questions."
		)
	try:
		frappe.sendmail(recipients=[user.email], subject=subject, message=body, delayed=True)
	except Exception:
		pass  # email may not be set up; the account works either way
