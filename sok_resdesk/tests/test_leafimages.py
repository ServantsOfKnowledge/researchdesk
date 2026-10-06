"""0.55: a folder of photographs becomes a book through an ingest run: its leaves, page images at any
size, OCR for printed ones, and a IIIF service that cuts regions. The search engine is stood in for."""

import io
import json
import os
import shutil
import tempfile
from unittest import mock

import frappe
from PIL import Image

from sok_resdesk.tests.test_operations import OpsTestCase

ID = "img-palm-Ramayana-bundle"
PRINTED = "img-printed-Hymns"


def photo(path, size, colour):
	Image.new("RGB", size, colour).save(path, "JPEG")


class TestPhotographBooks(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit", "ocr_scans": 1})
		self.root = tempfile.mkdtemp(prefix="rd-leaves-")
		frappe.local.conf["resdesk_library_roots"] = [self.root]
		bundle = os.path.join(self.root, "palm", "Ramayana bundle")
		os.makedirs(bundle)
		for n, colour in ((1, (200, 50, 50)), (2, (50, 200, 50)), (10, (50, 50, 200))):
			photo(os.path.join(bundle, f"leaf{n}.jpg"), (3000, 400), colour)
		with open(os.path.join(bundle, "bundle.json"), "w") as f:
			json.dump(
				{
					"title": "Ramayana",
					"creator": ["Valmiki"],
					"language": "san",
					"manuscript": {"script": "Grantha", "material": "Palm leaf"},
				},
				f,
			)
		printed = os.path.join(self.root, "printed", "Hymns")
		os.makedirs(printed)
		for n in (1, 2):
			photo(os.path.join(printed, f"{n}.jpg"), (800, 1100), (240, 240, 240))
		with open(os.path.join(printed, "bundle.json"), "w") as f:
			json.dump({"item_type": "Book", "title": "Hymns"}, f)
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
				"profile_name": "rdtest leaves",
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

		for name in (ID, PRINTED):
			pdfs.forget_pages(name)
		for name in frappe.get_all("RD Item", filters={"name": ("like", "img-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": "Valmiki"})
		frappe.local.conf.pop("resdesk_library_roots", None)
		shutil.rmtree(self.root, ignore_errors=True)
		frappe.db.commit()

	def run_profile(self):
		from sok_resdesk.ingest import create_run, run_ingest

		run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
		frappe.db.commit()
		run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_a_folder_of_photographs_is_a_manuscript_with_its_leaves(self):
		run = self.run_profile()
		self.assertEqual((run.status, run.created_count), ("Completed", 2), run.log)
		book = frappe.get_doc("RD Item", ID)
		self.assertEqual(
			(book.title, book.item_type, book.source, book.page_count), ("Ramayana", "Manuscript", "Local", 3)
		)
		self.assertEqual(
			book.local_images.splitlines(), ["leaf1.jpg", "leaf2.jpg", "leaf10.jpg"]
		)  # 2 before 10
		self.assertEqual((book.ms_script, book.ms_material), ("Grantha", "Palm leaf"))
		self.assertIn("page_image?item_id=img-palm-Ramayana-bundle&leaf=0&width=300", book.thumbnail_url)
		self.assertFalse(book.has_page_text)  # a manuscript is transcribed by people, not read with OCR
		self.assertEqual(
			[kw["item_id"] for m, kw in self.enqueued if m == "sok_resdesk.pdfs.ocr_book"], [PRINTED]
		)
		# a person's edit to the details is never undone by the next run
		frappe.db.set_value("RD Item", ID, "ms_script", "Tigalari")
		self.run_profile()
		self.assertEqual(frappe.db.get_value("RD Item", ID, "ms_script"), "Tigalari")

	def test_the_page_images_at_any_size_and_for_ocr(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api, pdfs

		self.run_profile()
		frappe.db.set_value("RD Item", ID, {"published": 1, "visibility": "Public", "access_status": "Open"})
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Administrator")  # page images are for members (staff are members)
		try:
			small = api.page_image(ID, 2, 600)
			whole = api.page_image(ID, 2)
			two = api.page_image(
				ID, 1, 99999
			)  # never more than 4000 wide, and never more than the photograph
		finally:
			frappe.set_user("Administrator")
		sizes = []
		for resp in (small, whole, two):
			resp.direct_passthrough = False
			sizes.append(Image.open(io.BytesIO(resp.get_data())).size)
		self.assertEqual(sizes, [(600, 80), (3000, 400), (3000, 400)])
		self.assertEqual(Image.open(io.BytesIO(pdfs.page_png(ID, 0))).mode, "L")  # grey, for Tesseract
		got = api.page(ID, 2)
		self.assertIn("width=1600", got["image"])

	def test_the_iiif_service_cuts_regions_from_a_photograph(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import iiif

		self.run_profile()
		frappe.db.set_single_value("RD Settings", "feature_sharing", 1)
		frappe.db.set_value("RD Item", ID, {"published": 1, "visibility": "Public", "access_status": "Open"})
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.set_user("Guest")
		try:
			info = iiif.image_info(ID, "0")
			data = json.loads(info.get_data(as_text=True))
			self.assertEqual((data["profile"], data["width"], data["height"]), ("level2", 3000, 400))
			self.assertEqual(data["tiles"][0]["scaleFactors"], [1, 2, 4, 8])
			tile = iiif.image(ID, "0", "0,0,512,400/256,/0/default.jpg")
			tile.direct_passthrough = False
			with Image.open(io.BytesIO(tile.get_data())) as im:
				self.assertEqual(im.size, (256, 200))
				r, g, b = im.getpixel((10, 10))
				self.assertGreater(r, 150)  # leaf 1 is red
			mid = iiif.image(ID, "1", "full/200,/180/default.png")
			mid.direct_passthrough = False
			with Image.open(io.BytesIO(mid.get_data())) as im:
				self.assertEqual(im.size, (200, 27))
				self.assertGreater(im.getpixel((10, 10))[1], 150)  # leaf 2 is green
			manifest = json.loads(iiif.manifest(ID).get_data(as_text=True))
			self.assertEqual(len(manifest["items"]), 3)
			self.assertEqual(
				manifest["items"][0]["items"][0]["items"][0]["body"]["service"][0]["profile"], "level2"
			)
		finally:
			frappe.set_user("Administrator")
