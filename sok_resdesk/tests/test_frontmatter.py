"""Details read from the title pages: drafted, checked, applied."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import frontmatter

ITEM = "rdtestfront1"
PAGES = [
	{"leaf": 0, "label": "", "text": "A History of the Deccan"},
	{
		"leaf": 1,
		"label": "",
		"text": "First published 1950\nPublished by Sahitya Akademi, New Delhi\nISBN 978-0-306-40615-7",
	},
]


class TestFrontmatter(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._clean()
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": ITEM,
				"title": "A History of the Deccan",
				"language": "eng",
				"published": 1,
				"visibility": "Public",
				"has_page_text": 1,
				"place": "Mumbai",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.pages = mock.patch("sok_resdesk.ingest.fetch_pages", return_value=PAGES)
		self.fetch = self.pages.start()

	def tearDown(self):
		self.pages.stop()
		self._clean()
		frappe.set_user("Administrator")

	def _clean(self):
		frappe.db.delete("RD Metadata Suggestion", {"name": ITEM})
		frappe.db.delete("RD Suggested Detail", {"parent": ITEM})  # deleting the parent leaves its rows
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.db.commit()

	def test_a_draft_is_read_checked_and_applied(self):
		out = frontmatter.extract(ITEM)
		self.assertEqual(out["status"], "Draft")
		doc = frappe.get_doc("RD Metadata Suggestion", ITEM)
		rows = {r.field: r for r in doc.details}
		self.assertEqual(rows["publisher"].suggested, "Sahitya Akademi")
		self.assertEqual(rows["publisher"].decision, "Use This")
		self.assertEqual(rows["place"].decision, "Keep Current")  # the book already says Mumbai
		self.assertEqual(rows["year"].image_no, 2)
		frontmatter.decide(ITEM, "Applied")
		book = frappe.get_doc("RD Item", ITEM)
		self.assertEqual((book.publisher, book.year, book.place), ("Sahitya Akademi", 1950, "Mumbai"))
		self.assertTrue(book.lock_metadata)
		self.assertEqual(frappe.db.get_value("RD Metadata Suggestion", ITEM, "status"), "Applied")
		self.assertEqual(frontmatter.extract(ITEM)["status"], "Applied")  # not read over again

	def test_nothing_new_makes_no_draft(self):
		frappe.db.set_value(
			"RD Item",
			ITEM,
			{"publisher": "Sahitya Akademi", "place": "New Delhi", "year": 1950, "isbn": "978-0-306-40615-7"},
		)
		self.assertEqual(frontmatter.extract(ITEM)["status"], "")
		self.assertFalse(frappe.db.exists("RD Metadata Suggestion", ITEM))

	def test_the_assistant_fills_what_the_rules_missed(self):
		pages = [{"leaf": 0, "label": "", "text": "Printed for\nSahitya Akademi"}]
		reply = '{"publisher": "Sahitya Akademi", "year": "1999"}'  # the year is not on the page
		self.fetch.return_value = pages
		with (
			mock.patch("sok_resdesk.assistant.enabled", return_value=True),
			mock.patch("sok_resdesk.assistant.ask", return_value=reply),
		):
			self.assertEqual(frontmatter.extract(ITEM)["status"], "Draft")
		rows = {r.field: r for r in frappe.get_doc("RD Metadata Suggestion", ITEM).details}
		self.assertEqual(set(rows), {"publisher"})
		self.assertEqual(rows["publisher"].how, "Assistant")
