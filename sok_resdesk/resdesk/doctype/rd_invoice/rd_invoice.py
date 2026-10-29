# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk import acquisitions


class RDInvoice(Document):
	def validate(self):
		acquisitions.check_invoice(self)

	def on_trash(self):
		if self.status != "Draft":
			frappe.throw(_("An invoice that has been approved is cancelled, not deleted."))
