# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk.core import gst


class RDVendor(Document):
	def validate(self):
		self.gstin = (self.gstin or "").strip().upper()
		if self.gstin and not gst.valid_gstin(self.gstin):
			frappe.throw(_("{0} is not a valid GSTIN.").format(self.gstin))
