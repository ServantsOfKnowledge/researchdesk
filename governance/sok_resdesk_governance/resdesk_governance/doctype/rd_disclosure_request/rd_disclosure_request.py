# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDDisclosureRequest(Document):
	def validate(self):
		from sok_resdesk_governance import disclosure

		disclosure.on_validate(self)

	def after_insert(self):
		from sok_resdesk_governance import audit

		audit.record("disclosure_received", detail=f"{self.name}: {len(self.records or [])} records")

	def on_trash(self):
		frappe.throw(_("A disclosure request is kept as the record of what was asked and decided."))
