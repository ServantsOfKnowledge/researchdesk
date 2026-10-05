"""0.54: manuscripts and palm leaves: their own details, leaf labels in the reader and in search,
and transcribing a leaf nobody has read. The search engine is stood in for."""

import json
from unittest import mock

import frappe

from sok_resdesk import api, manuscripts, pagetext
from sok_resdesk.catalogue import item_to_record
from sok_resdesk.tests.test_operations import OpsTestCase

ITEM = "rdtest-palm-leaf"


class TestManuscripts(OpsTestCase):
	def setUp(self):
		super().setUp()
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.reindex_pages"),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(self._clean)
		self._clean()
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": ITEM,
				"title": "A palm-leaf bundle",
				"item_type": "Manuscript",
				"source": "Local",
				"page_count": 6,
				"published": 1,
				"visibility": "Public",
				"access_status": "Open",
				"ms_material": "Palm leaf",
				"ms_script": "Grantha",
				"ms_leaves": 3,
				"ms_colophon": "Copied in Śaka 1745",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Page Text", {"item": ITEM})
		frappe.delete_doc("RD Item", ITEM, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_manuscripts_own_details_travel_with_the_record(self):
		record = item_to_record(frappe.get_doc("RD Item", ITEM))
		got = {m["label"]: m["value"] for m in record["manuscript"]}
		self.assertEqual(
			got,
			{"Material": "Palm leaf", "Script": "Grantha", "Leaves": "3", "Colophon": "Copied in Śaka 1745"},
		)
		self.assertEqual(record["leaf_labels"], {})
		# a book has none of these
		frappe.db.set_value(
			"RD Item", ITEM, {"ms_material": "", "ms_script": "", "ms_leaves": 0, "ms_colophon": ""}
		)
		self.assertEqual(item_to_record(frappe.get_doc("RD Item", ITEM))["manuscript"], [])

	def test_labelling_the_leaves_shows_before_it_saves(self):
		with mock.patch("frappe.enqueue") as queued:
			shown = manuscripts.label_leaves(ITEM, "a/b", 2, 4, 1, preview=1)
			self.assertEqual(
				[x["label"] for x in shown["labels"]], ["front 1", "1a", "1b", "2a", "2b", "end 1"]
			)
			self.assertFalse(frappe.db.get_value("RD Item", ITEM, "leaf_labels"))
			queued.assert_not_called()
			manuscripts.label_leaves(ITEM, "a/b", 2, 4, 1)
			queued.assert_called_once()
		self.assertEqual(json.loads(frappe.db.get_value("RD Item", ITEM, "leaf_labels"))["1"], "1a")
		self.assertEqual(item_to_record(frappe.get_doc("RD Item", ITEM))["leaf_labels"][2], "1b")
		with mock.patch("frappe.enqueue"):
			manuscripts.clear_labels(ITEM)
		self.assertFalse(frappe.db.get_value("RD Item", ITEM, "leaf_labels"))

	def test_a_leaf_without_text_still_has_its_label_in_the_reader(self):
		with mock.patch("frappe.enqueue"):
			manuscripts.label_leaves(ITEM, "r/v", 1, 0, 1)
		got = api.page(ITEM, 1)
		self.assertEqual((got["label"], got["has_text"], got["text"]), ("1v", False, ""))
		self.assertEqual(api.page(ITEM, 2)["label"], "2r")

	def test_a_leaf_nobody_has_read_is_transcribed_from_nothing(self):
		self.assertFalse(frappe.db.get_value("RD Item", ITEM, "has_page_text"))
		with mock.patch("frappe.enqueue"):
			manuscripts.label_leaves(ITEM, "a/b", 1, 0, 1)
		frappe.set_user("Administrator")
		pagetext.save_page(ITEM, 3, "ಶ್ರೀ ಗಣಪತಯೇ ನಮಃ")
		self.assertEqual(frappe.db.get_value("RD Item", ITEM, ["has_page_text", "has_fulltext"]), (1, 1))
		got = api.page(ITEM, 3)
		self.assertEqual((got["text"], got["label"]), ("ಶ್ರೀ ಗಣಪತಯೇ ನಮಃ", "2b"))
		self.assertEqual(got["text_status"], "Proofread")
		# the leaf's label also rides on the text that search is given
		from sok_resdesk.ingest import fetch_pages

		self.assertEqual([(p["leaf"], p["label"]) for p in fetch_pages(ITEM)], [(3, "2b")])

	def test_only_staff_label_leaves_and_the_image_count_must_be_known(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			manuscripts.label_leaves(ITEM)
		frappe.set_user("Administrator")
		frappe.db.set_value("RD Item", ITEM, "page_count", 0)
		with self.assertRaisesRegex(frappe.ValidationError, "number of images"):
			manuscripts.label_leaves(ITEM)
