"""How a book can be used: Full, Read only (no downloads), Research only (no extractable text either)."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import access, api, iiif

ITEM = "rdtestuselevel1"
READER = "rdtestuselevel1@example.com"


class TestUseLevel(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._clean()
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": ITEM,
				"title": "A Research Collection",
				"language": "eng",
				"published": 1,
				"visibility": "Public",
			}
		).insert(ignore_permissions=True)
		access.add_reader(READER, "Test Reader", send_welcome=False)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		self._clean()

	def _clean(self):
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.db.delete("Has Role", {"parent": READER})
		frappe.db.delete("User", {"name": READER})
		frappe.db.commit()

	def level(self, level):
		frappe.db.set_value("RD Item", ITEM, "use_level", level)
		frappe.local.__dict__.pop("rd_use_levels", None)  # the per-request cache

	def can(self):
		v = "Public"
		return (
			access.can_read(v, item=ITEM),
			access.can_view_pages(v, item=ITEM),
			access.can_use_text(v, item=ITEM),
			access.can_download(v, item=ITEM),
		)

	def test_each_level_for_a_reader_and_for_staff(self):
		frappe.set_user(READER)
		self.level("Full")
		self.assertEqual(self.can(), (True, True, True, True))
		self.level("Read only")  # pages and their text on screen, no downloads
		self.assertEqual(self.can(), (True, True, True, False))
		self.level("Research only")  # pages as images, no text, no downloads
		self.assertEqual(self.can(), (True, True, False, False))
		frappe.set_user("Administrator")
		frappe.local.__dict__.pop("rd_use_levels", None)
		self.assertEqual(self.can(), (True, True, True, True))  # staff are not limited

	def test_a_restricted_book_cannot_be_downloaded_or_served_as_images(self):
		self.level("Read only")
		frappe.set_user(READER)
		self.assertRaises(frappe.PermissionError, api.book_text, ITEM, "txt")
		record, error = iiif._book(ITEM)
		self.assertEqual((record, error.status_code), (None, 403))
		self.assertFalse(api.item(ITEM)["pdf_url"])

	def test_only_managers_set_the_level_in_bulk(self):
		frappe.set_user(READER)
		self.assertRaises(frappe.PermissionError, access.bulk_set_use_level, "Read only", [ITEM])
		frappe.set_user("Administrator")
		out = access.bulk_set_use_level("Research only", names=[ITEM])
		self.assertEqual(out["count"], 1)
		self.assertEqual(frappe.db.get_value("RD Item", ITEM, "use_level"), "Research only")
		self.assertRaises(frappe.ValidationError, access.bulk_set_use_level, "Nonsense", names=[ITEM])

	def test_research_only_closes_the_text_paths_round_the_reader(self):
		from sok_resdesk import annotations

		self.level("Research only")
		frappe.set_user(READER)
		self.assertIsNone(annotations._page_text(ITEM, 0))  # a note could hand the text back
