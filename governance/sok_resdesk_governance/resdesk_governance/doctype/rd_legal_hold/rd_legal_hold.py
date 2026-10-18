# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDLegalHold(Document):
	def on_trash(self):
		frappe.throw(_("A legal hold is released, never deleted: its history is kept."))
