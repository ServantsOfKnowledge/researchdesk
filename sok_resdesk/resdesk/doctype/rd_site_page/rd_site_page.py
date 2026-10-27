# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document

from sok_resdesk import sitepages
from sok_resdesk.core import collections as core


class RDSitePage(Document):
	def autoname(self):
		self.slug = core.slugify(self.slug or self.title)
		self.name = self.slug

	def validate(self):
		if self.in_menu and self.members_only:
			self.in_menu = 0  # a link guests cannot use does not belong in the top bar
		if self.in_menu and not (self.menu_label or "").strip():
			self.menu_label = self.title

	def on_update(self):
		sitepages.sync_top_bar(self)
		frappe.clear_cache()

	def on_trash(self):
		self.in_menu = 0
		sitepages.sync_top_bar(self)
		frappe.clear_cache()
