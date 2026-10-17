"""0.78: classification and need-to-know under Governance Mode."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import access, classification


class TestGovernance(IntegrationTestCase):
	USER = "rdgovtest@example.com"

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.cache.delete_value("RD Settings")
		for name, parent in (
			("RD Test Head", None),
			("RD Test District", "RD Test Head"),
			("RD Test Other", None),
		):
			frappe.get_doc(
				{"doctype": "RD Department", "department_name": name, "parent_department": parent}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User", "email": self.USER, "first_name": "Gov", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Item", {"name": ("like", "rdgovtest%")})
		frappe.db.delete("RD Clearance", {"name": self.USER})
		frappe.db.delete("RD Department", {"name": ("like", "RD Test %")})
		frappe.db.delete("User", {"name": self.USER})
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.local.rd_clearance = {}
		frappe.db.commit()

	def item(self, n, **values):
		return frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": f"rdgovtest{n}",
				"title": f"Gov {n}",
				"visibility": "Public",
				**values,
			}
		).insert(ignore_permissions=True)

	def clear(self, level, *departments):
		frappe.local.rd_clearance = {}
		frappe.db.delete("RD Clearance", {"name": self.USER})
		frappe.get_doc(
			{
				"doctype": "RD Clearance",
				"user": self.USER,
				"level": level,
				"departments": [{"department": d} for d in departments],
			}
		).insert(ignore_permissions=True)

	def test_a_classified_record_becomes_cleared_only_and_comes_back(self):
		doc = self.item(1, classification="Confidential", department="RD Test District")
		self.assertEqual(
			(doc.visibility, doc.class_rank, doc.visibility_before), ("Cleared only", 2, "Public")
		)
		doc.classification, doc.department = "Unclassified", None
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.visibility, doc.class_rank), ("Public", 0))

	def test_a_head_office_is_cleared_for_its_district_not_the_reverse(self):
		self.clear("Confidential", "RD Test Head")
		self.assertTrue(access.is_cleared(2, "RD Test District", self.USER))
		self.assertFalse(access.is_cleared(3, "RD Test District", self.USER))
		self.assertFalse(access.is_cleared(0, "RD Test Other", self.USER))
		self.clear("Restricted", "RD Test District")
		self.assertFalse(access.is_cleared(1, "RD Test Head", self.USER))

	def test_nobody_has_a_clearance_by_role_and_a_guest_sees_nothing_classified(self):
		self.item(2, classification="Restricted")
		frappe.set_user("Guest")
		try:
			names = frappe.db.sql_list(
				f"select name from `tabRD Item` where name like 'rdgovtest%' and {access.sql_condition()}"
			)
		finally:
			frappe.set_user("Administrator")
		self.assertNotIn("rdgovtest2", names)

	def test_secret_needs_classified_mode(self):
		with self.assertRaises(frappe.ValidationError):
			self.item(3, classification="Secret")
		self.assertFalse(classification.classified_mode())

	def test_governance_cannot_be_switched_off_with_classified_records(self):
		self.item(4, classification="Restricted")
		settings = frappe.get_doc("RD Settings")
		settings.governance = 0
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)
