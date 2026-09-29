# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class RDItem(Document):
	def validate(self):
		names = []
		for row in self.creators or []:
			label = row.name_as_given or row.creator
			if label and label not in names:
				names.append(label)
		self.creator_display = "; ".join(names)
		if self.year and not (500 <= int(self.year) <= 2100):
			frappe.throw(frappe._("Year {0} looks wrong").format(self.year))

	def as_record(self) -> dict:
		"""Plain dict used by citations, MARC, OAI and the search index."""
		from sok_resdesk.catalogue import item_to_record

		return item_to_record(self)
