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

	@property
	def is_folder(self) -> bool:
		return self.source == "Folder or Server"

	def build_query(self) -> str:
		"""IA query, or a description of the folder/server for folder sources."""
		if self.is_folder:
			if not (self.location or "").strip():
				raise IAError("Folder path or server URL is empty")
			return f"items under {self.location.strip()}"
		if self.scope_type == "Metadata File":
			where = (self.metadata_path or "").strip() or (self.metadata_file or "").strip()
			if not where:
				raise IAError("Upload a metadata file, or give the path of one on the server")
			return f"records in {where}"
		return IAClient.build_query(
			self.scope_type,
			collection=self.ia_collection or "",
			extra_filter=self.extra_filter or "",
			query=self.ia_query or "",
			identifiers=(self.identifiers or "").splitlines(),
		)
