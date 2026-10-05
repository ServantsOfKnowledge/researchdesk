"""0.51: a Calibre library brought in through an ingest run: details, covers, downloads, PDF text.
The library is a real (small) Calibre layout on disk; the search engine is stood in for."""

import shutil
import tempfile
from unittest import mock

import frappe

from sok_resdesk.tests import calibre_fixtures as fx
from sok_resdesk.tests.test_operations import OpsTestCase


class TestCalibreImport(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit"})
		self.root = fx.make_library(tempfile.mkdtemp(prefix="rd-calibre-") + "/Calibre Library")
		self.base = self.root.rsplit("/", 1)[0]
		frappe.local.conf["resdesk_library_roots"] = [self.base]
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest calibre",
				"source": "Folder or Server",
				"location": self.root,
				"fetch_fulltext": 1,
				"check_archive_org": 1,  # a Calibre library is never looked for on archive.org
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._clean)

	def _clean(self):
		for name in frappe.get_all("RD Item", filters={"name": ("like", "calibre-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": ("in", ["Kanakadasa", "Smith, John"])})
		frappe.local.conf.pop("resdesk_library_roots", None)
		shutil.rmtree(self.base, ignore_errors=True)
		frappe.db.commit()

	def run_profile(self):
		from sok_resdesk.ingest import create_run, run_ingest

		with mock.patch("sok_resdesk.local_source.on_archive_org") as asked:
			run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
			frappe.db.commit()
			run_ingest(run.name, foreground=True)
		asked.assert_not_called()
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_the_library_comes_in_with_details_covers_and_files(self):
		from sok_resdesk.catalogue import item_to_record

		run = self.run_profile()
		self.assertEqual((run.status, run.created_count), ("Completed", 3), run.log)
		book = frappe.get_doc("RD Item", fx.ID_EPUB)
		self.assertEqual((book.title, book.source, book.year), ("Kirtanegalu", "Local", 1931))
		self.assertEqual(
			(book.publisher, book.language, book.series), ("Mysore Press", "mul", "Dasa Sahitya #2")
		)
		self.assertEqual(sorted(r.creator for r in book.creators), ["Kanakadasa", "Smith, John"])
		self.assertEqual(sorted(r.subject for r in book.subjects), ["devotional", "poetry"])
		self.assertEqual(book.local_pdf or "", "")  # an e-book: no PDF
		self.assertEqual(book.local_thumb, "cover.jpg")
		self.assertEqual(
			book.local_files.splitlines(), ["Kirtanegalu - Kanakadasa.epub", "Kirtanegalu - Kanakadasa.mobi"]
		)
		self.assertFalse(book.on_archive_org)
		self.assertFalse(book.has_page_text)  # e-book text is a follow-up
		record = item_to_record(book)
		self.assertEqual([d["label"] for d in record["downloads"]], ["EPUB", "MOBI"])
		self.assertEqual(record["pdf_url"], "")

	def test_a_pdf_in_the_library_gives_its_text(self):
		from sok_resdesk.ingest import fetch_pages

		self.run_profile()
		book = frappe.get_doc("RD Item", fx.ID_PDF)
		self.assertEqual((book.text_source, book.page_count), ("PDF text layer", 2))
		self.assertEqual(fetch_pages(fx.ID_PDF)[1]["text"], fx.PDF_PAGES[1])
		self.assertEqual(book.local_pdf, "Typed notes - John Smith.pdf")
		self.assertEqual(book.year or 0, 0)  # Calibre's "no date" is not a year

	def test_the_library_is_left_as_it_was_and_a_second_run_changes_nothing(self):
		import hashlib

		def digest():
			return hashlib.sha1(open(self.root + "/metadata.db", "rb").read()).hexdigest()

		before = digest()
		self.run_profile()
		modified = frappe.db.get_value("RD Item", fx.ID_EPUB, "modified")
		again = self.run_profile()
		self.assertEqual(again.created_count, 0)
		self.assertEqual(frappe.db.get_value("RD Item", fx.ID_EPUB, "modified"), modified)
		self.assertEqual(digest(), before)

	def test_readers_download_the_formats_by_the_books_own_access(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api

		self.run_profile()
		frappe.db.set_value("RD Item", fx.ID_EPUB, {"visibility": "Public", "published": 1})
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Guest")
		try:
			response = api.file(fx.ID_EPUB, "Kirtanegalu - Kanakadasa.epub")
			response.direct_passthrough = False
			self.assertEqual(response.get_data(), fx.EPUB)
			api.file(fx.ID_EPUB, "cover.jpg")
			# only what the record lists: not the OPF, not another book's file
			for name in ("metadata.opf", "../Typed notes (2)/Typed notes - John Smith.pdf"):
				self.assertRaises(frappe.PageDoesNotExistError, api.file, fx.ID_EPUB, name)
			# members-only (login to read): the cover may show, the files are for readers
			frappe.set_user("Administrator")
			frappe.db.set_value("RD Item", fx.ID_EPUB, "visibility", "Login to read")
			frappe.set_user("Guest")
			self.assertRaises(
				(frappe.PermissionError, frappe.PageDoesNotExistError),
				api.file,
				fx.ID_EPUB,
				"Kirtanegalu - Kanakadasa.epub",
			)
		finally:
			frappe.set_user("Administrator")
