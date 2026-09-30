# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document

from sok_resdesk.core.collections import slugify


class RDCollection(Document):
	def autoname(self):
		if not self.slug:
			self.slug = slugify(self.title)
		base, n = self.slug, 2
		while frappe.db.exists("RD Collection", self.slug):
			self.slug = f"{base}-{n}"
			n += 1
		self.name = self.slug

	def validate(self):
		if self.slug:
			self.slug = slugify(self.slug)

	@property
	def route(self):
		return f"/library/collection/{self.name}"
