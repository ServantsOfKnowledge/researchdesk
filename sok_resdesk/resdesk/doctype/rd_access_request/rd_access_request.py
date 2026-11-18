# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, nowdate


class RDAccessRequest(Document):
	def validate(self):
		if frappe.db.exists(
			"RD Access Request", {"item": self.item, "user": self.user, "name": ("!=", self.name)}
		):
			frappe.throw(_("This reader already has a request for this book."))
		if not self.is_new() and self.has_value_changed("status") and self.status in ("Approved", "Declined"):
			self.decided_by = frappe.session.user
			self.decided_on = now_datetime()
			if self.status == "Approved" and not self.valid_until:
				days = frappe.db.get_single_value("RD Settings", "access_valid_days") or 0
				self.valid_until = add_days(nowdate(), days) if days else None
		if self.status != "Approved":
			self.valid_until = None

	def on_update(self):
		if self.has_value_changed("status") and self.status in ("Approved", "Declined"):
			from sok_resdesk.approval import tell_reader

			tell_reader(self)
