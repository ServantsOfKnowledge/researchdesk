# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk.core.ia import IAClient, IAError


class RDIngestProfile(Document):
	def validate(self):
		if self.max_items is not None and self.max_items < 0:
			frappe.throw(_("Maximum Items cannot be negative"))
		try:
			self.build_query()
		except IAError as e:
			frappe.throw(str(e))

	def build_query(self) -> str:
		return IAClient.build_query(
			self.scope_type,
			collection=self.ia_collection or "",
			extra_filter=self.extra_filter or "",
			query=self.ia_query or "",
			identifiers=(self.identifiers or "").splitlines(),
		)
