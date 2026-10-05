"""0.40: scans without text. Loose PDFs in a folder become books; a PDF with a text layer gives
its text, a scan is read with OCR in the background; pages are drawn from the PDF for Page &
text. Tesseract and the drawing of pages are stood in for; the catalogue and the run are real."""

import os
import shutil
import tempfile
from unittest import mock

import frappe

from sok_resdesk.tests.oai_fixtures import make_pdf
from sok_resdesk.tests.test_operations import OpsTestCase
from sok_resdesk.tests.unit_pdfs import scan_pdf


class TestScansWithoutText(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit", "ocr_scans": 1})
		self.root = tempfile.mkdtemp(prefix="rd-pdfs-")
		frappe.local.conf["resdesk_library_roots"] = [self.root]
		os.makedirs(os.path.join(self.root, "theses"))
		with open(os.path.join(self.root, "theses", "rdtestpdf Text thesis.pdf"), "wb") as f:
			f.write(make_pdf(["The first page of a born-digital thesis", "Its second page, with words"]))
		with open(os.path.join(self.root, "theses", "rdtestpdf Old scan.pdf"), "wb") as f:
			f.write(scan_pdf(2))
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
			mock.patch("sok_resdesk.core.ocr_engine.available", return_value=["eng", "kan"]),
		):
			p.start()
			self.addCleanup(p.stop)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest pdfs",
				"source": "Folder or Server",
				"location": self.root,
				"fetch_fulltext": 1,
				"check_archive_org": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._clean)

	def _clean(self):
		from sok_resdesk import pdfs

		for name in ("rdtestpdf-Text-thesis", "rdtestpdf-Old-scan"):
			pdfs.forget_pages(name)
			for path in (pdfs._ocr_path(name),):
				if os.path.exists(path):
					os.remove(path)
		frappe.db.delete("RD Item", {"name": ("like", "rdtestpdf%")})
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.local.conf.pop("resdesk_library_roots", None)
		shutil.rmtree(self.root, ignore_errors=True)
		frappe.db.commit()

	def test_loose_pdfs_their_text_and_ocr_for_the_scan(self):
		from sok_resdesk import pdfs
		from sok_resdesk.ingest import create_run, fetch_pages, run_ingest

		run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
		frappe.db.commit()
		run_ingest(run.name, foreground=True)
		run = frappe.get_doc("RD Ingest Run", run.name)
		self.assertEqual((run.status, run.created_count), ("Completed", 2), run.log)

		text = frappe.get_doc("RD Item", "rdtestpdf-Text-thesis")
		self.assertEqual((text.title, text.source), ("rdtestpdf Text thesis", "Local"))
		self.assertEqual((text.text_source, text.page_count), ("PDF text layer", 2))
		self.assertTrue(text.has_page_text)
		self.assertEqual(fetch_pages(text.name)[1]["text"], "Its second page, with words")

		scan = frappe.get_doc("RD Item", "rdtestpdf-Old-scan")
		self.assertEqual((scan.text_source, scan.page_count), (pdfs.SCAN, 2))
		self.assertFalse(scan.has_page_text)
		queued = [kw for method, kw in self.enqueued if method == "sok_resdesk.pdfs.ocr_book"]
		self.assertEqual([kw["item_id"] for kw in queued], [scan.name])

		# the OCR job: every page drawn and read; the text becomes the book's
		read = mock.patch(
			"sok_resdesk.core.ocr_engine.read_page",
			side_effect=lambda img, z, m: {"text": f"ಓದಿದ ಪುಟ {len(img) > 0}"},
		)
		with read, mock.patch("sok_resdesk.reocr.engine_name", return_value="tesseract 5 (kan+eng)"):
			result = pdfs.ocr_book(scan.name)
		self.assertEqual(result, {"read": 2, "failed": 0})
		scan.reload()
		self.assertTrue(scan.has_page_text)
		self.assertEqual(scan.text_source, "OCR here (tesseract 5 (kan+eng))")
		self.assertEqual([p["text"] for p in fetch_pages(scan.name)], ["ಓದಿದ ಪುಟ True"] * 2)
		self.assertIn("read with OCR", scan.reocr_state)

		# ingested again (the folder changed): the OCR'd text is kept, not read again
		self.enqueued.clear()
		from sok_resdesk.local_source import ingest_local_one, open_profile_store

		store = open_profile_store(self.profile)
		loc = dict(store.iter_items())[scan.name]
		ingest_local_one(store, scan.name, loc, self.profile, fetch_text=True, force=True)
		scan.reload()
		self.assertEqual(scan.text_source, "OCR here")
		self.assertTrue(scan.has_page_text)
		self.assertFalse([m for m, _kw in self.enqueued if m == "sok_resdesk.pdfs.ocr_book"])

	def test_pages_are_drawn_for_page_and_text(self):
		from sok_resdesk import api, pdfs
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.local_source import ingest_local_one, open_profile_store

		store = open_profile_store(self.profile)
		loc = dict(store.iter_items())["rdtestpdf-Text-thesis"]
		ingest_local_one(store, "rdtestpdf-Text-thesis", loc, self.profile, fetch_text=True)
		record = item_to_record(frappe.get_doc("RD Item", "rdtestpdf-Text-thesis"))
		self.assertTrue(pdfs.has_pdf(record))
		url = api.page_image_url(record, 1)
		self.assertIn("sok_resdesk.api.page_image?item_id=rdtestpdf-Text-thesis&leaf=1", url)
		with mock.patch("sok_resdesk.pdfs.render", return_value=b"\xff\xd8jpeg") as drawn:
			self.assertEqual(pdfs.page_jpeg("rdtestpdf-Text-thesis", 1), b"\xff\xd8jpeg")
			self.assertEqual(pdfs.page_jpeg("rdtestpdf-Text-thesis", 1), b"\xff\xd8jpeg")  # kept once drawn
		self.assertEqual(drawn.call_count, 1)
		# the re-OCR of a page (proofreading) gets its image from the PDF too
		from sok_resdesk import reocr

		with mock.patch("sok_resdesk.pdfs.render", return_value=b"png") as png:
			self.assertEqual(reocr.page_image("rdtestpdf-Text-thesis", 0), b"png")
		self.assertEqual(png.call_args.args[1:], (0, 300))
