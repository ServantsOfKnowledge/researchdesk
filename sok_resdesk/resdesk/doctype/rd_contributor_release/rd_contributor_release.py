# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class RDContributorRelease(Document):
	"""One person's open licence for the pages they proofread (see sok_resdesk/groundtruth.py)."""

	def validate(self):
		if self.is_new():
			self.user = frappe.session.user  # only ever one's own
		if self.has_value_changed("licence") or self.is_new() or not self.agreed_on:
			self.agreed_on = now_datetime()
