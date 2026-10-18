# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk import register


class RDFile(Document):
	def before_naming(self):
		register.number(self)

	def validate(self):
		register.on_validate(self)

	def on_update(self):
		register.on_update(self)

	def on_trash(self):
		frappe.throw(_("A file is closed, never deleted: the register is the record."))
