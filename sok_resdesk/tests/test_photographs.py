"""0.58: photographs as items, and manuscripts and photographs as features of the institutions that
keep them. Through an ingest run on a folder; the search engine is stood in for."""

import io
import json
import os
import shutil
import tempfile
from unittest import mock

import frappe
from PIL import Image

from sok_resdesk.tests.test_operations import OpsTestCase
from sok_resdesk.tests.unit_photo import make_photo

PHOTO = "ph-Ratha-at-dusk"
PLAIN = "ph-IMG_0042"


class TestPhotographs(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value(
			"RD Settings", {"book_limit": "No limit", "feature_photographs": 1, "feature_manuscripts": 1}
		)
		self.root = tempfile.mkdtemp(prefix="rd-photos-")
		frappe.local.conf["resdesk_library_roots"] = [self.root]
		folder = os.path.join(self.root, "1987")
		os.makedirs(folder)
		make_photo(os.path.join(folder, "Ratha at dusk.jpg"))
		with open(os.path.join(folder, "Ratha at dusk.json"), "w", encoding="utf-8") as f:
			json.dump(
				{
					"title": "The ratha at dusk",
					"subject": ["festivals", "Udupi"],
					"photo": {"people": ["A priest"], "place": "Udupi", "depicts": ["Q1234"]},
				},
				f,
			)
		make_photo(os.path.join(folder, "IMG_0042.jpg"), with_exif=False)
		# a folder of images that are the leaves of one manuscript
		leaves = os.path.join(self.root, "palm", "Bundle")
		os.makedirs(leaves)
		for n in (1, 2):
			Image.new("RGB", (900, 120), (90, 60, 30)).save(os.path.join(leaves, f"leaf{n}.jpg"))
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.photos = self.profile(
			"rdtest photos", images_as_photographs=1, location=os.path.join(self.root, "1987")
		)
		self.bundles = self.profile("rdtest bundles", location=os.path.join(self.root, "palm"))
		frappe.db.commit()
		self.addCleanup(self._clean)

	def profile(self, name, **kw):
		return frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": name,
				"source": "Folder or Server",
				"location": self.root,
				"fetch_fulltext": 1,
				"check_archive_org": 0,
				**kw,
			}
		).insert(ignore_permissions=True)

	def _clean(self):
		from sok_resdesk import pdfs

		for name in frappe.get_all("RD Item", filters={"name": ("like", "img-%")}, pluck="name") + [
			PHOTO,
			PLAIN,
		]:
			pdfs.forget_pages(name)
		for name in frappe.get_all(
			"RD Item", filters={"name": ("like", "img-%")}, pluck="name"
		) + frappe.get_all("RD Item", filters={"name": ("like", "ph-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		for p in (self.photos, self.bundles):
			frappe.db.delete("RD Ingest Run", {"profile": p.name})
			frappe.db.delete("RD Ingest Profile", p.name)
		frappe.local.conf.pop("resdesk_library_roots", None)
		frappe.db.set_single_value("RD Settings", {"feature_photographs": 1, "feature_manuscripts": 1})
		shutil.rmtree(self.root, ignore_errors=True)
		frappe.db.commit()

	def run_profile(self, profile):
		from sok_resdesk.ingest import create_run, run_ingest

		run = create_run(frappe.get_doc("RD Ingest Profile", profile.name), "Manual")
		frappe.db.commit()
		run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_every_image_is_a_photograph_with_its_exif_and_its_own_words(self):
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.core import photo

		run = self.run_profile(self.photos)
		self.assertEqual((run.status, run.created_count), ("Completed", 2), run.log)
		p = frappe.get_doc("RD Item", PHOTO)
		self.assertEqual(
			(p.title, p.item_type, p.page_count, p.source), ("The ratha at dusk", "Photograph", 1, "Local")
		)
		self.assertEqual(p.local_images, "Ratha at dusk.jpg")
		self.assertEqual(
			(p.ph_taken_on, p.ph_camera, p.ph_place, p.ph_depicts),
			("1987-03-14", "Nikon FM2", "Udupi", "Q1234"),
		)
		self.assertEqual(
			(p.ph_gps, p.ph_dimensions, p.ph_people), ("13.333333, 74.75", "640 × 480 px", "A priest")
		)
		self.assertEqual(sorted(r.subject for r in p.subjects), ["Udupi", "festivals"])
		self.assertEqual(p.ph_sha256, photo.sha256_of(os.path.join(self.root, "1987", "Ratha at dusk.jpg")))
		self.assertEqual(p.year, 1987)  # from the camera's date
		self.assertIn("leaf=0&width=300", p.thumbnail_url)
		self.assertFalse(p.has_page_text)
		labels = [r["label"] for r in item_to_record(p)["photograph"]]
		self.assertEqual(labels[:3], ["Taken on", "Place", "People shown"])
		plain = frappe.get_doc("RD Item", PLAIN)  # no EXIF, no words: the file's name and its size
		self.assertEqual(
			(plain.title, plain.item_type, plain.ph_dimensions), ("IMG 0042", "Photograph", "640 × 480 px")
		)
		self.assertFalse(plain.ph_taken_on)

	def test_a_persons_edit_to_a_photograph_survives_a_second_run_and_the_original_is_checked(self):
		self.run_profile(self.photos)
		frappe.db.set_value("RD Item", PHOTO, {"ph_place": "Mangaluru"})
		again = self.run_profile(self.photos)
		self.assertEqual(again.created_count, 0)
		# the original changed: the next run notices, and keeps the person's place
		path = os.path.join(self.root, "1987", "Ratha at dusk.jpg")
		before = frappe.db.get_value("RD Item", PHOTO, "ph_sha256")
		Image.new("RGB", (640, 480), (1, 2, 3)).save(path, "JPEG")
		later = os.stat(path).st_mtime + 10
		os.utime(path, (later, later))
		self.run_profile(self.photos)
		self.assertNotEqual(frappe.db.get_value("RD Item", PHOTO, "ph_sha256"), before)
		self.assertEqual(frappe.db.get_value("RD Item", PHOTO, "ph_place"), "Mangaluru")

	def test_without_the_option_a_folder_of_images_is_one_manuscript(self):
		run = self.run_profile(self.bundles)
		self.assertEqual(run.created_count, 1, run.log)
		self.assertEqual(frappe.db.get_value("RD Item", "img-Bundle", "item_type"), "Manuscript")

	def test_the_features_decide_what_is_collected_and_what_can_be_done(self):
		from sok_resdesk import features, manuscripts

		frappe.db.set_single_value("RD Settings", "feature_photographs", 0)
		self.assertEqual(self.run_profile(self.photos).created_count, 0)  # not collected
		self.assertFalse(frappe.db.exists("RD Item", PHOTO))
		frappe.db.set_single_value("RD Settings", "feature_manuscripts", 0)
		self.assertEqual(self.run_profile(self.bundles).created_count, 0)
		frappe.db.set_single_value("RD Settings", "feature_manuscripts", 1)
		self.run_profile(self.bundles)
		frappe.db.set_single_value("RD Settings", "feature_manuscripts", 0)
		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			manuscripts.label_leaves("img-Bundle")
		features.apply()

	def test_profiles_say_who_keeps_manuscripts_and_photographs(self):
		from sok_resdesk import features

		for key in ("manuscripts", "photos"):
			self.assertIn("photographs", features.PROFILES[key].features)
		self.assertIn("manuscripts", features.PROFILES["manuscripts"].features)
		self.assertNotIn("manuscripts", features.PROFILES["photos"].features)
		self.assertNotIn("photographs", features.PROFILES["portal"].features)
		self.assertNotIn("manuscripts", features.PROFILES["small"].features)

	def test_the_photograph_is_zoomable_and_a_iiif_manifest(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api, iiif

		self.run_profile(self.photos)
		frappe.db.set_value(
			"RD Item", PHOTO, {"published": 1, "visibility": "Public", "access_status": "Open"}
		)
		frappe.db.set_single_value("RD Settings", "feature_sharing", 1)
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Guest")
		try:
			got = api.page(PHOTO, 0)
			self.assertIn("page_image", got["image"])
			tile = iiif.image(PHOTO, "0", "100,100,200,100/100,/0/default.jpg")
			tile.direct_passthrough = False
			self.assertEqual(Image.open(io.BytesIO(tile.get_data())).size, (100, 50))
			m = json.loads(iiif.manifest(PHOTO).get_data(as_text=True))
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(len(m["items"]), 1)
