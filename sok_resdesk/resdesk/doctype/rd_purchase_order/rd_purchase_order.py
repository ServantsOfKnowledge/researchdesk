# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document


class RDPurchaseOrder(Document):
	def validate(self):
		self.total = round(sum((r.quantity or 0) * (r.unit_price or 0) for r in self.lines), 2)
