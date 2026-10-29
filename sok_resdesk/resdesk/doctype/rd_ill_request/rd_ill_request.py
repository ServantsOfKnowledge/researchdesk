# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class RDILLRequest(Document):
	def validate(self):
		if self.direction == "Borrowing" and not self.patron:
			frappe.throw(_("Choose the member the book is for."))
		if self.direction == "Lending" and not (self.partner_library or "").strip():
			frappe.throw(_("Say which library is asking."))
		if flt(self.fee) < 0:
			frappe.throw(_("The fee cannot be negative."))
		if not self.requested_on:
			self.requested_on = nowdate()
