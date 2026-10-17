# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk.core import classification as levels


class RDClearance(Document):
	def validate(self):
		if self.level not in levels.allowed_levels(bool(frappe.conf.get("resdesk_classified"))):
			frappe.throw(
				_("{0} needs Classified mode, which this installation was not set up with.").format(
					self.level
				)
			)
		# nobody grants beyond their own clearance or edits their own (the built-in Administrator can)
		if frappe.session.user != "Administrator":
			from sok_resdesk import access

			rank, departments = access.clearance()
			if self.user == frappe.session.user:
				frappe.throw(_("You cannot change your own clearance."))
			if levels.rank(self.level) > rank:
				frappe.throw(_("You cannot grant a level above your own clearance."))
			given = {d.department for d in self.departments or []}
			if departments is not None and (not given or not given <= departments):
				frappe.throw(_("You can only grant departments that are within your own clearance."))
