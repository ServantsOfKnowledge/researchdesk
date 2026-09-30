# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document


class RDExport(Document):
	def after_insert(self):
		from sok_resdesk.transfer import start_export

		start_export(self.name)
