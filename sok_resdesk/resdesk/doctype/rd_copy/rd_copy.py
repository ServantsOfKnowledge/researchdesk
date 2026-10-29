# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class RDCopy(Document):
	def before_naming(self):
		self.barcode = (self.barcode or "").strip().upper() or make_autoname("C-.######")

	def validate(self):
		if not frappe.db.exists("RD Item", self.item):
			frappe.throw(_("Choose the catalogue record this is a copy of."))
		if self.flags.from_lending or self.is_new() and self.status not in ("On loan", "On hold shelf"):
			return
		before = self.get_doc_before_save()
		was = before.status if before else None
		if self.status != was and (
			self.status in ("On loan", "On hold shelf") or was in ("On loan", "On hold shelf")
		):
			frappe.throw(_("Lend, return and shelve copies at the Circulation Desk."))
