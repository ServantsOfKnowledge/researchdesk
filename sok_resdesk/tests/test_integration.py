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
