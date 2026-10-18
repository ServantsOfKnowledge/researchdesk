# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class RDDisposal(Document):
	"""Made and changed only by sok_resdesk_governance.retention (daily list, approve, cancel, execute): a hand-made
	or hand-edited list could name records that were never due."""

	def validate(self):
		if not frappe.flags.rd_retention:
			frappe.throw(_("A Disposal is made and changed only by Research Desk's retention rules."))

	def on_trash(self):
		frappe.throw(_("A Disposal is kept as the record of what was done."))
