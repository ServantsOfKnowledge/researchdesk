# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from sok_resdesk.core.ia import IAClient, IAError

REPOSITORY = "Repository (OAI-PMH)"
WIKISOURCE = "Wikisource"
IDS_IN_ONE_QUERY = 100  # identifiers per archive.org search (a longer address is refused)


class RDIngestProfile(Document):
	def validate(self):
		from sok_resdesk import features

		if self.is_new() or self.has_value_changed("source"):
			features.require_source(self.source)  # Settings → Features
		if self.max_items is not None and self.max_items < 0:
			frappe.throw(_("Maximum Items cannot be negative"))
		try:
			self.build_query()
		except IAError as e:
			frappe.throw(str(e))
		if self.is_repository:
			self._repository_defaults()
		if self.is_wikisource:
			self.keep_in_sync = 0
			self.catalogue_first = 0
			self.wiki_site = (self.wiki_site or "").strip()

	def _repository_defaults(self):
		"""An identifier prefix (from the repository's address when none is given), letters,
		digits and hyphens only; and nothing archive.org-only switched on."""
		import re
		from urllib.parse import urlparse

		prefix = (self.id_prefix or "").strip()
		if not prefix:
			host = urlparse((self.oai_url or "").strip()).hostname or "repo"
			parts = [p for p in host.split(".") if p not in ("www", "dspace", "eprints", "repository", "oai")]
			prefix = parts[0] if parts else "repo"
		self.id_prefix = re.sub(r"[^a-z0-9-]+", "-", prefix.lower()).strip("-") or "repo"
		self.oai_prefix = (self.oai_prefix or "").strip() or "oai_dc"
		self.keep_in_sync = 0
		self.catalogue_first = 0

	@property
	def is_folder(self) -> bool:
		return self.source == "Folder or Server"

	@property
	def is_repository(self) -> bool:
		return self.source == REPOSITORY

	@property
	def is_wikisource(self) -> bool:
		return self.source == WIKISOURCE

	@property
	def on_archive_org(self) -> bool:
		return not (self.is_folder or self.is_repository or self.is_wikisource)

	def identifier_list(self) -> list[str]:
		"""The profile's identifiers, once each, in order (one per line; commas and spaces too)."""
		import re

		return list(dict.fromkeys(t for t in re.split(r"[\s,]+", self.identifiers or "") if t))

	def build_query(self) -> str:
		"""IA query, or a description of the folder/server for folder sources."""
		if self.is_folder:
			if not (self.location or "").strip():
				raise IAError("Folder path or server URL is empty")
			return f"items under {self.location.strip()}"
		if self.is_repository:
			if not (self.oai_url or "").strip():
				raise IAError("Give the repository's OAI-PMH address")
			return f"records at {self.oai_url.strip()}" + (
				f" in set {self.oai_set.strip()}" if self.oai_set else ""
			)
		if self.is_wikisource:
			if not (self.wiki_site or "").strip():
				raise IAError("Give the Wikisource's address, e.g. kn.wikisource.org")
			if not (self.wiki_category or "").strip() and not (self.wiki_indexes or "").strip():
				raise IAError("Give a category of Index pages, or list Index pages")
			return f"books on {self.wiki_site.strip()}" + (
				f" in {self.wiki_category.strip()}" if (self.wiki_category or "").strip() else ""
			)
		if self.scope_type == "Metadata File":
			where = (self.metadata_path or "").strip() or (self.metadata_file or "").strip()
			if not where:
				raise IAError("Upload a metadata file, or give the path of one on the server")
			return f"records in {where}"
		if self.scope_type == "Identifier List":
			ids = self.identifier_list()
			if not ids:
				raise IAError("Identifier list is empty")
			if len(ids) > IDS_IN_ONE_QUERY:  # far too long for one archive.org search: listed as is
				return f"{len(ids):,} identifiers listed on the profile"
		return IAClient.build_query(
			self.scope_type,
			collection=self.ia_collection or "",
			extra_filter=self.extra_filter or "",
			query=self.ia_query or "",
			identifiers=(self.identifiers or "").splitlines(),
			media=bool(self.get("include_media")),
		)
