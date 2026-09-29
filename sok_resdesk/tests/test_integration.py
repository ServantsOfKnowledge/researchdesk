"""Frappe integration tests (need a site; no network).

bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app sok_resdesk
"""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk.catalogue import get_record, upsert_item
from sok_resdesk.core.normalize import normalize_ia_item
from sok_resdesk.search import build_filter, doc_id

META = {
	"identifier": "rdtest.sample0001",
	"title": "ವಚನ ಸಂಪುಟ",
	"alt_title": "Vachana Samputa",
	"creator": ["ಡಾ. ಎಂ. ಎಂ. ಕಲಬುರ್ಗಿ", "ಬಸವರಾಜ"],
	"alt_creator": ["Dr. M. M. Kalburgi", "Basavaraja"],
	"date": "1993-01-01",
	"language": "Kannada",
	"subject": ["Vachana", "Kannada literature"],
	"collection": ["ServantsOfKnowledge", "fav-someone"],
	"imagecount": "240",
	"publisher": "Kannada Pustaka Pradhikara",
}


class TestResearchDesk(IntegrationTestCase):
	def setUp(self):
		self.record = normalize_ia_item(META["identifier"], META, [])
		upsert_item(self.record, raw=META)

	def tearDown(self):
		frappe.db.rollback()

	def test_upsert_creates_linked_records(self):
		doc = frappe.get_doc("RD Item", "rdtest.sample0001")
		self.assertEqual(doc.year, 1993)
		self.assertEqual(doc.language, "kan")
		self.assertEqual(len(doc.creators), 2)
		self.assertTrue(frappe.db.exists("RD Creator", "ಡಾ. ಎಂ. ಎಂ. ಕಲಬುರ್ಗಿ"))
		self.assertEqual(frappe.db.get_value("RD Creator", "ಬಸವರಾಜ", "alt_name"), "Basavaraja")
		self.assertEqual({r.subject for r in doc.subjects}, {"Vachana", "Kannada literature"})
		self.assertNotIn("fav-someone", doc.collections)

	def test_upsert_is_idempotent(self):
		_, created = upsert_item(self.record)
		self.assertFalse(created)
		self.assertEqual(frappe.db.count("RD Item", {"name": "rdtest.sample0001"}), 1)

	def test_record_round_trip(self):
		record = get_record("rdtest.sample0001")
		self.assertEqual(record["alt_creators"], ["Dr. M. M. Kalburgi", "Basavaraja"])
		self.assertEqual(record["decade"], "1990s")

	def test_unpublished_records_are_hidden(self):
		frappe.db.set_value("RD Item", "rdtest.sample0001", "published", 0)
		self.assertIsNone(get_record("rdtest.sample0001"))

	def test_cite_endpoint(self):
		from sok_resdesk.api import cite

		resp = cite("rdtest.sample0001", "bibtex")
		body = resp.get_data(as_text=True)
		self.assertIn("@book{kalburgi1993vachana", body)
		self.assertIn("application/x-bibtex", resp.headers["Content-Type"])

	def test_oai_store(self):
		from sok_resdesk.oai import FrappeStore

		store = FrappeStore()
		self.assertIsNotNone(store.get("rdtest.sample0001"))
		items, total = store.list(0, 100000, None, None, "ServantsOfKnowledge")
		self.assertIn("rdtest.sample0001", [i["item_id"] for i in items])
		self.assertIsNotNone(items[0]["modified"].tzinfo)

	def test_search_helpers(self):
		self.assertEqual(doc_id("abc-1"), "abc-1")
		self.assertTrue(doc_id("a.b").startswith("a_b-"))
		f = build_filter({"language_label": ["Kannada"], "year_from": 1900, "bogus": ["x"]})
		self.assertEqual(f, [['language_label = "Kannada"'], "year >= 1900"])


class TestLocalFolderSource(IntegrationTestCase):
	"""Folder source end to end, without network (archive.org check off)."""

	def setUp(self):
		import gzip
		import json
		import os
		import tempfile

		self.root = tempfile.mkdtemp(prefix="rd-lib-")
		frappe.local.conf["resdesk_library_roots"] = [self.root]
		d = os.path.join(self.root, "shelf", "rdtest.local0001")
		os.makedirs(d)
		with open(os.path.join(d, "rdtest.local0001_meta.xml"), "w", encoding="utf-8") as f:
			f.write("<metadata><identifier>rdtest.local0001</identifier><title>ಸ್ಥಳೀಯ ಪುಸ್ತಕ</title>"
					"<creator>ಲೇಖಕ</creator><language>kan</language><date>1950</date></metadata>")
		with open(os.path.join(d, "rdtest.local0001.pdf"), "wb") as f:
			f.write(b"%PDF-1.4\n%test")
		text = "ಮೊದಲ ಪುಟ\nಎರಡನೇ ಪುಟ"
		with open(os.path.join(d, "rdtest.local0001_hocr_searchtext.txt.gz"), "wb") as f:
			f.write(gzip.compress(text.encode()))
		with open(os.path.join(d, "rdtest.local0001_hocr_pageindex.json.gz"), "wb") as f:
			f.write(gzip.compress(json.dumps([[0, 8, 0, 0], [9, 19, 0, 0]]).encode()))
		self.profile = frappe._dict(name=None, location=self.root, manifest_url="", check_archive_org=0)

	def tearDown(self):
		import shutil

		frappe.db.rollback()
		frappe.local.conf.pop("resdesk_library_roots", None)
		shutil.rmtree(self.root, ignore_errors=True)

	def test_ingest_local_item_and_skip_unchanged(self):
		from sok_resdesk import search
		from sok_resdesk.local_source import ingest_local_one, open_profile_store

		search.index_record = lambda *a, **k: 2  # keep the search engine out of this test
		store = open_profile_store(self.profile)
		items = list(store.iter_items())
		self.assertEqual(items, [("rdtest.local0001", "shelf/rdtest.local0001")])
		outcome, _ = ingest_local_one(store, *items[0], self.profile, fetch_text=True)
		self.assertEqual(outcome, "created")
		doc = frappe.get_doc("RD Item", "rdtest.local0001")
		self.assertEqual((doc.source, doc.on_archive_org, doc.local_pdf, doc.text_source),
						 ("Local", 0, "rdtest.local0001.pdf", "hocr_searchtext"))
		record = get_record("rdtest.local0001")
		self.assertIn("sok_resdesk.api.file", record["pdf_url"])
		self.assertEqual(ingest_local_one(store, *items[0], self.profile, fetch_text=True)[0], "unchanged")

	def test_folder_outside_library_roots_is_refused(self):
		from sok_resdesk.local_source import open_profile_store

		with self.assertRaises(frappe.ValidationError):
			open_profile_store(frappe._dict(location="/etc", manifest_url=""))
