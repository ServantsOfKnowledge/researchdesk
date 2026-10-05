# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils.nestedset import NestedSet

from sok_resdesk.core import archival


class RDArchivalUnit(NestedSet):
	"""One unit of archival description: a fonds, series, file or item, in a hierarchy (ISAD(G))."""

	nsm_parent_field = "parent_unit"

	def validate(self):
		self.ref_code = (self.ref_code or "").strip()
		if not archival.valid_code(self.ref_code):
			frappe.throw(
				_("The reference code may hold letters, digits and . _ - only (it is in the web address).")
			)
		parent_level = (
			frappe.db.get_value("RD Archival Unit", self.parent_unit, "level") if self.parent_unit else ""
		)
		problem = archival.child_allowed(parent_level or "", self.level)
		if problem:
			frappe.throw(_(problem))
		if self.parent_unit == self.name:
			frappe.throw(_("A unit cannot be part of itself."))
		self.is_group = 0 if self.level == "Item" else 1
		self.year_from, self.year_to = cint(self.year_from) or None, cint(self.year_to) or None
		if self.year_from and self.year_to and self.year_to < self.year_from:
			frappe.throw(_("The last year is before the first."))

	def on_update(self):
		super().on_update()

	def on_trash(self):
		if frappe.db.exists("RD Item", {"archival_unit": self.name}):
			frappe.throw(_("Digitised items are attached to this unit: move them first."))
		super().on_trash()
