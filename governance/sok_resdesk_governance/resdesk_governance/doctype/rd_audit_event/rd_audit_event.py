# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDAuditEvent(Document):
	"""Written only by sok_resdesk_governance.audit; never changed or removed afterwards."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("The audit log cannot be changed."))

	def on_trash(self):
		if not frappe.flags.in_test:
			frappe.throw(_("The audit log cannot be deleted."))
