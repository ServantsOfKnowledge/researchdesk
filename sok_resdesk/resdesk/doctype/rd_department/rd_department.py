# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDDepartment(Document):
	def validate(self):
		if "%" in (self.department_name or ""):
			frappe.throw(_("A department name cannot contain %."))
		# an office cannot report to itself or to one of its own subordinates
		above, seen = self.parent_department, {self.name}
		while above:
			if above in seen:
				frappe.throw(_("{0} would end up reporting to itself.").format(self.department_name))
			seen.add(above)
			above = frappe.db.get_value("RD Department", above, "parent_department")
