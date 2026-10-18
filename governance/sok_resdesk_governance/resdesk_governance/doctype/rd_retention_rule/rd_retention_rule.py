# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDRetentionRule(Document):
	def validate(self):
		if (self.years or 0) < 1:
			frappe.throw(_("A rule keeps records for at least one year."))
