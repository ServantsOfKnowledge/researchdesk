# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class RDMessage(Document):
	def validate(self):
		if not self.is_new() and self.has_value_changed("status"):
			self.handled_by = frappe.session.user
			self.handled_on = now_datetime()

	def after_insert(self):
		from sok_resdesk.contact import after_message

		after_message(self)
