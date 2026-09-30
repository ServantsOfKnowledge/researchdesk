# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


class RDItem(Document):
	def validate(self):
		names = []
		for row in self.creators or []:
			label = row.name_as_given or row.creator
			if label and label not in names:
				names.append(label)
		self.creator_display = "; ".join(names)
		if self.year and not (500 <= int(self.year) <= 2100):
			frappe.throw(frappe._("Year {0} looks wrong").format(self.year))
		self.visibility = self.visibility or "Public"
		self.item_type = self.item_type or "Book"
		self._lock_manual_edits()
		# a change made in this form is a deliberate choice: "Apply Access Rules" leaves it alone
		if (self.is_new() and not self.visibility_set_by) or (
			not self.is_new() and self.has_value_changed("visibility")
		):
			self.visibility_set_by = "Manual"

	def _lock_manual_edits(self):
		"""An edit made by a person (Desk form, bulk edit, spreadsheet import) should survive the
		next re-ingest, so switch on Keep My Edits."""
		if self.is_new() or self.flags.from_ingest or self.lock_metadata:
			return
		from sok_resdesk.catalogue import DESCRIPTIVE

		before = self.get_doc_before_save()
		if not before:
			return
		changed = any((self.get(f) or "") != (before.get(f) or "") for f in DESCRIPTIVE)
		people = [(r.creator, r.name_as_given) for r in self.creators or []]
		changed = changed or people != [(r.creator, r.name_as_given) for r in before.creators or []]
		changed = changed or [r.subject for r in self.subjects or []] != [
			r.subject for r in before.subjects or []
		]
		if changed:
			self.lock_metadata = 1

	def on_update(self):
		# collection counts follow the Collections field
		before = self.get_doc_before_save()
		old = {r.collection for r in (before.get("curated_collections") or [])} if before else set()
		new = {r.collection for r in self.get("curated_collections") or []}
		if old != new:
			from sok_resdesk.curation import refresh_counts

			refresh_counts(list(old ^ new))

	def as_record(self) -> dict:
		"""Plain dict used by citations, MARC, OAI and the search index."""
		from sok_resdesk.catalogue import item_to_record

		return item_to_record(self)
