# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

from frappe.model.document import Document

from sok_resdesk_governance import classification


class RDItemScope(Document):
	def validate(self):
		classification.on_scope_validate(self)

	def on_update(self):
		classification.apply_to_item(self.item)

	def on_trash(self):
		classification.release_item(self)
