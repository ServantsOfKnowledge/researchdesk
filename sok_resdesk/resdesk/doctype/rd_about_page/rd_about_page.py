# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk import about


class RDAboutPage(Document):
	def validate(self):
		for field in ("primary_link", "secondary_link"):
			self._check_link(self.get(field), self.meta.get_label(field))
		for table in ("steps", "highlights"):
			for row in self.get(table):
				self._check_link(
					row.link, _("Link in row {0} of {1}").format(row.idx, self.meta.get_label(table))
				)

	def _check_link(self, link, label):
		if link and not about.safe_link(link):
			frappe.throw(
				_("{0}: give a page of this site (starting with /) or a web address (https://…).").format(
					label
				)
			)

	def on_update(self):
		about.sync_top_bar(self)
		frappe.clear_cache()  # the page and the top bar are cached
