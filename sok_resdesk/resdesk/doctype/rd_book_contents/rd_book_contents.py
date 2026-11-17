# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document


class RDBookContents(Document):
	def validate(self):
		for row in self.entries or []:
			row.title = (row.title or "").strip()
			row.level = min(max(row.level or 1, 1), 4)
