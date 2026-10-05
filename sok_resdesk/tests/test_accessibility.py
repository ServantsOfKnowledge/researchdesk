"""Integration tests for 0.35: a book's text to download (EPUB 3, plain text) and the help's
pictures of the library itself (Server page → Retake help pictures)."""

import io
import os
import zipfile
from unittest import mock

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase, _item

PAGES = [
	{"leaf": 0, "label": "", "text": "ಕನಕದಾಸ\nಎರಡನೆಯ ಸಾಲು"},
	{"leaf": 1, "label": "1", "text": "Second page", "status": "Proofread"},
]


class TestBookText(OpsTestCase):
	def _get(self, item, fmt):
		from sok_resdesk import api

		with mock.patch("sok_resdesk.ingest.fetch_pages", return_value=PAGES):
			return api.book_text(item, fmt)

	def test_epub_and_plain_text(self):
		item = _item(1)
		frappe.db.set_value("RD Item", item, {"has_page_text": 1, "language": "kan"})
		resp = self._get(item, "epub")
		self.assertEqual(resp.content_type, "application/epub+zip")
		self.assertIn(f'filename="{item}.epub"', resp.headers["Content-Disposition"])
		z = zipfile.ZipFile(io.BytesIO(resp.get_data()))
		self.assertIn("<dc:language>kn</dc:language>", z.read("EPUB/package.opf").decode())
		self.assertIn("1 of 2 pages were proofread", z.read("EPUB/package.opf").decode())
		text = self._get(item, "txt").get_data(as_text=True)
		self.assertIn("--- 1 ---\nSecond page", text)
		self.assertRaises(frappe.ValidationError, self._get, item, "pdf")

	def test_members_only_books_need_a_login(self):
		item = _item(2)
		frappe.db.set_value("RD Item", item, {"has_page_text": 1, "visibility": "Login to read"})
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, self._get, item, "epub")

	def test_no_text_no_file(self):
		item = _item(3)
		frappe.db.set_value("RD Item", item, "has_page_text", 0)
		self.assertRaises(frappe.ValidationError, self._get, item, "txt")


class TestHelpPictures(OpsTestCase):
	def test_the_librarys_own_picture_comes_first(self):
		from sok_resdesk import help as rd_help
		from sok_resdesk.core import helpdocs

		name = "rdtest-picture.png"
		from sok_resdesk import __version__

		self.assertEqual(rd_help.image_url(name), f"{helpdocs.IMAGE_URL}/{name}?v={__version__}")
		folder = frappe.get_site_path("public", "files", rd_help.SITE_PICTURES)
		os.makedirs(folder, exist_ok=True)
		path = os.path.join(folder, name)
		with open(path, "wb") as f:
			f.write(b"\x89PNG")
		self.addCleanup(os.remove, path)
		self.assertTrue(rd_help.image_url(name).startswith(f"/files/{rd_help.SITE_PICTURES}/{name}?v="))

	def test_the_server_page_can_ask_for_them(self):
		from sok_resdesk import server

		self.assertIn("help_pictures", server.ACTIONS)
		options = frappe.get_meta("RD Server Task").get_field("action").options.split("\n")
		self.assertIn("help_pictures", options)


class TestDefaultOrder(OpsTestCase):
	def test_oldest_first_unless_the_reader_chooses(self):
		from sok_resdesk.api import effective_sort

		frappe.db.set_single_value(
			"RD Settings", {"default_sort": "Oldest first", "relevance_when_searching": 1}
		)
		self.assertEqual(effective_sort("", ""), "year:asc")
		self.assertEqual(effective_sort("", "kanakadasa"), "")  # best matches first when searching
		self.assertEqual(effective_sort("relevance", ""), "")
		self.assertEqual(effective_sort("year:desc", "x"), "year:desc")
		self.assertEqual(effective_sort("drop table", ""), "year:asc")
		frappe.db.set_single_value("RD Settings", "relevance_when_searching", 0)
		self.assertEqual(effective_sort("", "kanakadasa"), "year:asc")
		frappe.db.set_single_value("RD Settings", "default_sort", "Newest first")
		self.assertEqual(effective_sort("", ""), "year:desc")
