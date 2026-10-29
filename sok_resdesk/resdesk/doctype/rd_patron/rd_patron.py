# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from sok_resdesk.core import lending


class RDPatron(Document):
	def on_trash(self):
		frappe.db.delete(
			"__Auth", {"doctype": "RD Patron", "name": self.name}
		)  # a kiosk PIN goes with the member

	def validate(self):
		self.institution_id = (self.institution_id or "").strip()
		if self.institution_id:
			same = frappe.db.get_value(
				"RD Patron",
				{
					"institution_id": self.institution_id,
					"name": ("!=", self.name),
					"status": ("!=", "Rejected"),
				},
				"name",
			)
			if same and self.status != "Rejected":
				frappe.throw(_("{0} already has this ID number.").format(same))
		if self.user and frappe.db.exists("RD Patron", {"user": self.user, "name": ("!=", self.name)}):
			frappe.throw(_("That portal account already belongs to another member."))
		if self.status == "Active" and not self.valid_until and self.is_new():
			months = frappe.db.get_value("RD Patron Category", self.category, "validity_months")
			self.valid_until = lending.membership_end(getdate(nowdate()), int(months or 0))
		if self.status == "Active" and self.valid_until and getdate(self.valid_until) < getdate(nowdate()):
			self.status = "Expired"
		if self.status == "Expired" and self.valid_until and getdate(self.valid_until) >= getdate(nowdate()):
			self.status = "Active"  # renewed by setting a later date
