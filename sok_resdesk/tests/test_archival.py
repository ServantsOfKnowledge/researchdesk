"""0.64: archival description: the hierarchy, its rules, who sees what, EAD3 and the item's place in it."""

from xml.etree import ElementTree as ET

import frappe

from sok_resdesk import archival
from sok_resdesk.core.archival import NS
from sok_resdesk.tests.test_operations import OpsTestCase, _item

PREFIX = "RDT-"


def unit(code, level, parent="", **kw):
	return frappe.get_doc(
		{
			"doctype": "RD Archival Unit",
			"ref_code": PREFIX + code,
			"title": f"Unit {code}",
			"level": level,
			"parent_unit": (PREFIX + parent) if parent else "",
			"published": 1,
			**kw,
		}
	).insert(ignore_permissions=True)


class TestArchival(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", "feature_archival", 1)
		self.addCleanup(self._clean)
		self._clean()
		self.fonds = unit("F", "Fonds", scope_content="One.\n\nTwo.", creator="A. Scholar", year_from=1900)
		self.series = unit("F-S", "Series", "F")
		self.item = unit("F-S-1", "Item", "F-S")
		self.book = _item(81)

	def _clean(self):
		frappe.db.set_value("RD Item", {"archival_unit": ("like", PREFIX + "%")}, "archival_unit", None)
		for name in reversed(
			frappe.get_all("RD Archival Unit", filters={"name": ("like", PREFIX + "%")}, pluck="name")
		):
			frappe.delete_doc("RD Archival Unit", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_hierarchy_is_checked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "reference code"):
			unit("bad code/1", "Series", "F")
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing is described under an item"):
			unit("F-S-1-x", "File", "F-S-1")
		with self.assertRaisesRegex(frappe.ValidationError, "no parent"):
			unit("F2", "Fonds", "F")
		with self.assertRaisesRegex(frappe.ValidationError, "sits inside a fonds or collection"):
			unit("S9", "Series")
		self.assertEqual(frappe.db.get_value("RD Archival Unit", self.item.name, "is_group"), 0)
		self.assertEqual(frappe.db.get_value("RD Archival Unit", self.fonds.name, "is_group"), 1)

	def test_a_unit_page_has_its_trail_parts_and_digitised_items(self):
		frappe.db.set_value(
			"RD Item", self.book, {"archival_unit": self.series.name, "published": 1, "visibility": "Public"}
		)
		page = archival.unit_page(self.series.name)
		self.assertEqual([u["name"] for u in page["trail"]], [self.fonds.name])
		self.assertEqual([u["name"] for u in page["children"]], [self.item.name])
		self.assertEqual([i.name for i in page["items"]], [self.book])
		top = archival.unit_page(self.fonds.name)
		self.assertEqual((top["count"], top["ead"]), (2, True))
		self.assertEqual(
			[u["name"] for u in archival.item_trail(self.book)], [self.fonds.name, self.series.name]
		)

	def test_a_hidden_series_hides_what_is_under_it(self):
		frappe.db.set_value("RD Archival Unit", self.series.name, "published", 0)
		frappe.set_user("Guest")
		try:
			self.assertIsNone(archival.unit_page(self.series.name))
			self.assertIsNone(archival.unit_page(self.item.name))  # its parent is hidden
			self.assertIsNotNone(archival.unit_page(self.fonds.name))
			self.assertEqual(archival.unit_page(self.fonds.name)["children"], [])
		finally:
			frappe.set_user("Administrator")

	def test_ead3_of_a_fonds_is_nested(self):
		units = archival._all()
		xml = archival.archival.ead3(
			self.fonds.name, [u for u in units if u["name"].startswith(PREFIX)], "Lib", "2026-11-06"
		)
		root = ET.fromstring(xml)
		n = {"e": NS}
		self.assertEqual(root.find("e:archdesc/e:did/e:unitid", n).text, PREFIX + "F")
		self.assertEqual(root.find("e:archdesc/e:dsc/e:c/e:c", n).get("level"), "item")

	def test_a_unit_with_digitised_items_cannot_be_deleted(self):
		frappe.db.set_value("RD Item", self.book, "archival_unit", self.series.name)
		with self.assertRaisesRegex(frappe.ValidationError, "Digitised items"):
			frappe.delete_doc("RD Archival Unit", self.series.name, force=False, ignore_permissions=True)

	def test_switched_off_there_is_nothing(self):
		frappe.db.set_single_value("RD Settings", "feature_archival", 0)
		frappe.clear_cache()
		self.assertIsNone(archival.unit_page(self.fonds.name))
		self.assertEqual(archival.top_units(), [])
