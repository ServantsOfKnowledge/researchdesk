"""The table of contents of a book: read into a draft, checked by a person, published to readers."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import access, contents

ITEM = "rdtestcontents1"
PAGES = [
	{"leaf": 0, "label": "", "text": "A History of the Deccan"},
	{
		"leaf": 1,
		"label": "",
		"text": "CONTENTS\n\nPreface ...... v\n1. Introduction ...... 1\n2. The Early Dynasties ...... 14\n3. Inscriptions ...... 42\nIndex ...... 310\n",
	},
	{"leaf": 2, "label": "", "text": "Preface\nThis book began as a lecture."},
	{"leaf": 3, "label": "", "text": "1. Introduction\nThe story begins in the north."},
]


class TestContents(IntegrationTestCase):
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
		frappe.db.delete("RD Book Contents", {"name": ITEM})
		frappe.db.delete("RD Contents Entry", {"parent": ITEM})  # deleting the parent leaves its rows
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.db.commit()

	def test_a_draft_is_read_checked_published_and_withdrawn(self):
		out = contents.extract(ITEM)
		self.assertEqual(out["status"], "Draft")
		self.assertEqual(out["entries"], 5)
		doc = frappe.get_doc("RD Book Contents", ITEM)
		self.assertEqual(doc.contents_pages, "2")  # the second page image
		# printed page 1 is image 4 (leaf 3): the offset carries to the others
		pages = {r.page_label: r.image_no for r in doc.entries}
		self.assertEqual((pages["1"], pages["14"], pages["310"]), (4, 17, 313))
		self.assertFalse(pages["v"])  # a roman page has no image number (an empty Int is stored as 0)
		# readers see nothing until it is published
		self.assertEqual(contents.published(ITEM), [])
		contents.set_status(ITEM, "Published")
		shown = contents.published(ITEM)
		self.assertEqual(shown[1], {"title": "1. Introduction", "page": "1", "leaf": 3, "level": 1})
		# a published list is not read over
		self.assertEqual(contents.extract(ITEM)["status"], "Published")
		contents.set_status(ITEM, "Draft")
		self.assertEqual(contents.published(ITEM), [])

	def test_a_book_with_no_contents_page_gets_no_draft(self):
		with mock.patch("sok_resdesk.ingest.fetch_pages", return_value=PAGES[:1] + PAGES[2:]):
			out = contents.extract(ITEM)
		self.assertEqual(out["status"], "")
		self.assertFalse(frappe.db.exists("RD Book Contents", ITEM))

	def test_only_managers_run_it_over_many_books(self):
		frappe.set_user("Guest")
		try:
			for roles, allowed in (({"ResDesk Cataloguer"}, False), ({"ResDesk Manager"}, True)):
				with (
					mock.patch.object(access, "_roles", return_value=roles),
					mock.patch.object(access, "select_items", return_value=[]),
				):
					if allowed:
						self.assertEqual(contents.bulk(names="[]")["count"], 0)
					else:
						self.assertRaises(frappe.PermissionError, contents.bulk, names="[]")
		finally:
			frappe.set_user("Administrator")

	def test_the_assistant_reads_contents_the_rules_could_not(self):
		pages = [{"leaf": 0, "label": "", "text": "Preface v\n1. Introduction 1\n2. The Early Dynasties 14"}]
		reply = '{"entries": [{"title": "Preface", "page": "v"}, {"title": "1. Introduction", "page": "1"}]}'
		self.fetch.return_value = pages
		with (
			mock.patch("sok_resdesk.assistant.enabled", return_value=True),
			mock.patch("sok_resdesk.assistant.ask", return_value=reply),
		):
			self.assertEqual(contents.extract(ITEM)["entries"], 2)
		doc = frappe.get_doc("RD Book Contents", ITEM)
		self.assertTrue(doc.by_assistant)
		self.assertEqual([r.title for r in doc.entries], ["Preface", "1. Introduction"])
