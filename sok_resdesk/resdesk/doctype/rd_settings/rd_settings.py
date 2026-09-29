# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class RDSettings(Document):
	def validate(self):
		if self.base_url:
			self.base_url = self.base_url.rstrip("/")
		if self.index_prefix:
			self.index_prefix = frappe.scrub(self.index_prefix)
