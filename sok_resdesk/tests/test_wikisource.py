"""0.48: books from Wikisource, through a whole ingest run. The wiki's API is stood in for
(sok_resdesk/tests/wikisource_fixtures.py); the catalogue, the run and its batches are real."""

from unittest import mock

import frappe

from sok_resdesk.core import wikisource as ws
from sok_resdesk.tests import wikisource_fixtures as fx
from sok_resdesk.tests.test_operations import OpsTestCase
from sok_resdesk.tests.wikisource_fixtures import Resp, Session

ITEM = "ws-kn-Kanaka.pdf"


class TestWikisourceSource(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit"})
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(self._clean)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest wikisource",
				"source": "Wikisource",
				"wiki_site": "kn.wikisource.org",
				"wiki_indexes": "Kanaka.pdf",
				"wiki_quality": "Proofread",
				"fetch_fulltext": 1,
				"max_items": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def _clean(self):
		for name in frappe.get_all("RD Item", filters={"name": ("like", "ws-kn-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)  # with its rows
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": ("in", ["Kanakadasa", "Other Poet"])})
		frappe.db.commit()

	def wiki(self):
		"""The wiki answering what a book needs, whichever way it is asked."""

		class Answers(Session):
			def get(this, url, params=None, timeout=None):
				this.asked.append(params)
				params = params or {}
				if params.get("meta") == "siteinfo":
					return Resp(fx.SITEINFO)
				if params.get("prop") == "imageinfo":
					return Resp(fx.FILEINFO)
				if params.get("generator") == "allpages":
					return Resp(fx.PAGES)
				return Resp(fx.INDEX_API)

		return ws.WikiClient("kn.wikisource.org", delay=0, session=Answers())

	def run_profile(self):
		from sok_resdesk.ingest import create_run, run_ingest

		with mock.patch("sok_resdesk.wikisource.client", side_effect=lambda profile: self.wiki()):
			run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
			frappe.db.commit()
			run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_a_book_with_its_proofread_pages(self):
		run = self.run_profile()
		self.assertEqual((run.status, run.created_count), ("Completed", 1), run.log)
		book = frappe.get_doc("RD Item", ITEM)
		self.assertEqual(book.source, "Wikisource")
		self.assertEqual((book.title, book.year, book.language), ("ಕನಕದಾಸ ಕೀರ್ತನೆಗಳು", 1931, "kan"))
		self.assertEqual((book.wiki_site, book.wiki_index), ("kn.wikisource.org", "Index:Kanaka.pdf"))
		self.assertEqual(book.source_url, "https://kn.wikisource.org/wiki/Index:Kanaka.pdf")
		self.assertEqual(book.page_count, 5)  # the scan's pages, not only those transcribed
		self.assertEqual(book.licence_url, ws.LICENCE)
		self.assertFalse(book.on_archive_org)
		# proofread and validated pages only: the unchecked and the blank page are left out
		self.assertEqual(book.text_source, "Wikisource (proofread)")
		from sok_resdesk.ingest import fetch_pages

		pages = fetch_pages(ITEM)
		self.assertEqual([p["leaf"] for p in pages], [0, 1])
		self.assertEqual(pages[1]["text"], "ಎರಡನೇ ಪುಟ")
		authors = sorted(r.creator for r in book.creators)
		self.assertEqual(authors, ["Kanakadasa", "Other Poet"])

	def test_the_pages_taken_follow_the_level(self):
		frappe.db.set_value("RD Ingest Profile", self.profile.name, "wiki_quality", "Any text")
		self.run_profile()
		book = frappe.get_doc("RD Item", ITEM)
		self.assertEqual(book.text_source, "Wikisource")  # not all proofread
		from sok_resdesk.ingest import fetch_pages

		self.assertEqual([p["leaf"] for p in fetch_pages(ITEM)], [0, 1, 2])
		frappe.db.set_value("RD Ingest Profile", self.profile.name, "wiki_quality", "Validated")
		self.run_profile()
		self.assertEqual([p["leaf"] for p in fetch_pages(ITEM)], [0])

	def test_page_images_come_from_the_wiki_and_the_book_is_a_iiif_manifest(self):
		self.run_profile()
		from sok_resdesk import api, iiif
		from sok_resdesk.catalogue import item_to_record

		record = item_to_record(frappe.get_doc("RD Item", ITEM))
		self.assertEqual(
			api.page_image_url(record, 1),
			"https://kn.wikisource.org/wiki/Special:Redirect/file/Kanaka.pdf?page=2&width=1000",
		)
		frappe.set_user("Guest")
		try:
			resp = iiif.manifest(ITEM)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(resp.status_code, 200)
		manifest = frappe.parse_json(resp.get_data(as_text=True))
		self.assertEqual(len(manifest["items"]), 5)
		body = manifest["items"][0]["items"][0]["items"][0]["body"]
		self.assertIn("Special:Redirect/file/Kanaka.pdf?page=1", body["id"])

	def test_an_unchanged_book_is_left_alone(self):
		self.run_profile()
		modified = frappe.db.get_value("RD Item", ITEM, "modified")
		second = self.run_profile()
		self.assertEqual(second.created_count, 0)
		self.assertEqual(frappe.db.get_value("RD Item", ITEM, "modified"), modified)

	def test_switched_off_with_the_repositories_feature(self):
		s = frappe.get_single("RD Settings")
		s.feature_repositories = 0
		s.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.set_single_value("RD Settings", "feature_repositories", 1))
		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": "rdtest wikisource 2",
					"source": "Wikisource",
					"wiki_site": "kn.wikisource.org",
					"wiki_indexes": "X.pdf",
				}
			).insert(ignore_permissions=True)
