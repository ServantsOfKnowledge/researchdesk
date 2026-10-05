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

	# -- 0.52: a set of books written out as a Calibre folder ---------------------------------------

	def test_exporting_writes_the_files_held_here_and_lists_the_rest(self):
		import csv
		import io
		import os
		import zipfile

		from sok_resdesk import calibre_export, transfer

		self.run_profile()
		for name in (fx.ID_EPUB, fx.ID_PDF):
			frappe.db.set_value("RD Item", name, "published", 1)
		# a book of archive.org's: nothing of it is held here
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": "calibre-rdtest-ia",
				"title": "On archive.org",
				"source": "Internet Archive",
				"on_archive_org": 1,
				"access_status": "Open",
				"published": 1,
			}
		).insert(ignore_permissions=True)
		export = frappe.get_doc(
			{
				"doctype": "RD Export",
				"export_format": "Calibre library (zip)",
				"scope": "Selected Books",
				"filters_json": frappe.as_json([fx.ID_EPUB, fx.ID_PDF, fx.ID_BARE, "calibre-rdtest-ia"]),
			}
		).insert(ignore_permissions=True)
		export.reload()
		self.addCleanup(lambda: frappe.db.delete("File", {"attached_to_name": export.name}))
		self.assertEqual((export.status, export.item_count), ("Done", 2), export.log)
		path = frappe.get_site_path(export.file_url.lstrip("/"))
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		with zipfile.ZipFile(path) as z:
			names = z.namelist()
			self.assertTrue(any(n.endswith("Kirtanegalu - Kanakadasa.epub") for n in names))
			self.assertTrue(any(n.endswith("Kirtanegalu - Kanakadasa.mobi") for n in names))
			self.assertTrue(any(n.endswith("/cover.jpg") for n in names))
			self.assertTrue(any(n.endswith("Typed notes - Smith, John.pdf") for n in names))
			epub = next(n for n in names if n.endswith(".epub"))
			self.assertEqual(z.read(epub), fx.EPUB)
			rows = {
				r["identifier"]: r for r in csv.DictReader(io.StringIO(z.read("not-included.csv").decode()))
			}
		self.assertEqual(sorted(rows), [fx.ID_BARE, "calibre-rdtest-ia"])
		self.assertIn("archive.org", rows["calibre-rdtest-ia"]["why not included"])
		self.assertIn("archive.org/details/calibre-rdtest-ia", rows["calibre-rdtest-ia"]["where it is"])
		# the estimate says the same before anything is made
		est = calibre_export.estimate(
			{
				"export_format": "Calibre library (zip)",
				"scope": "Selected Books",
				"filters_json": export.filters_json,
			}
		)
		self.assertEqual((est["books"], est["with_files"], est["not_included"]), (4, 2, 2))
		# the quick portal download is for records, not files
		with self.assertRaisesRegex(frappe.ValidationError, "holds files"):
			transfer.build("Calibre library (zip)", [fx.ID_EPUB])

	def test_a_book_that_is_not_open_is_never_written_out(self):
		from sok_resdesk import calibre_export

		self.run_profile()
		frappe.db.set_value("RD Item", fx.ID_PDF, {"access_status": "Restricted", "published": 1})
		books, left = calibre_export.gather([fx.ID_PDF])
		self.assertEqual((books, [r["item_id"] for r in left]), ([], [fx.ID_PDF]))
		self.assertIn("Not open", left[0]["why"])

	def test_an_offline_copy_holds_open_public_books_and_only_the_details_of_the_rest(self):
		import os
		import zipfile

		from sok_resdesk import offline_export

		self.run_profile()
		frappe.db.set_value(
			"RD Item", fx.ID_EPUB, {"published": 1, "access_status": "Open", "visibility": "Public"}
		)
		frappe.db.set_value(
			"RD Item", fx.ID_PDF, {"published": 1, "access_status": "Open", "visibility": "Login to read"}
		)
		est = offline_export.estimate(
			{
				"export_format": "Offline copy (zip, for Kiwix)",
				"scope": "Selected Books",
				"filters_json": frappe.as_json([fx.ID_EPUB, fx.ID_PDF]),
			}
		)
		self.assertEqual((est["books"], est["with_files"], est["details_only"]), (2, 1, 1))
		export = frappe.get_doc(
			{
				"doctype": "RD Export",
				"export_format": "Offline copy (zip, for Kiwix)",
				"scope": "Selected Books",
				"filters_json": frappe.as_json([fx.ID_EPUB, fx.ID_PDF]),
			}
		).insert(ignore_permissions=True)
		export.reload()
		self.addCleanup(lambda: frappe.db.delete("File", {"attached_to_name": export.name}))
		self.assertEqual((export.status, export.item_count), ("Done", 2), export.log)
		path = frappe.get_site_path(export.file_url.lstrip("/"))
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		with zipfile.ZipFile(path) as z:
			names = z.namelist()
			self.assertIn("index.html", names)
			self.assertTrue(any(n.startswith("files/") and n.endswith(".epub") for n in names))
			self.assertFalse(any(n.endswith(".pdf") for n in names))  # the members-only book: no file
			self.assertEqual(sum(1 for n in names if n.startswith("books/")), 2)
