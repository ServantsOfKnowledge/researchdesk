"""0.85: counts on staff screens, files and records."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import dashboard, register, review


class TestGaps(IntegrationTestCase):
	DEPT = "RD Test Gaps"

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.cache.delete_value("RD Settings")
		frappe.get_doc({"doctype": "RD Department", "department_name": self.DEPT}).insert(
			ignore_permissions=True
		)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD File Record", {"parent": ("like", "RDGAPSTEST%")})
		frappe.db.delete("RD File", {"name": ("like", "RDGAPSTEST%")})
		frappe.db.delete("RD Review Flag", {"item": ("like", "rdgapstest%")})
		frappe.db.delete("RD Item Scope", {"item": ("like", "rdgapstest%")})
		frappe.db.delete("RD Item", {"name": ("like", "rdgapstest%")})
		frappe.db.delete("RD Department", {"name": self.DEPT})
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.db.commit()

	def item(self, n, classify=False):
		doc = frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": f"rdgapstest{n}",
				"title": f"Gaps {n}",
				"visibility": "Public",
				"published": 1,
			}
		).insert(ignore_permissions=True)
		if classify:
			frappe.get_doc(
				{
					"doctype": "RD Item Scope",
					"item": doc.name,
					"classification": "Restricted",
					"department": self.DEPT,
				}
			).insert(ignore_permissions=True)
		return doc.name

	def test_the_dashboard_does_not_count_a_classified_record(self):
		before = dashboard.count("RD Item", {"published": 1})
		self.item(1)
		assert dashboard.count("RD Item", {"published": 1}) == before + 1
		self.item(2, classify=True)
		assert dashboard.count("RD Item", {"published": 1}) == before + 1

	def test_a_classified_record_is_not_checked_or_queued(self):
		self.item(3)
		b = self.item(4, classify=True)
		review.scan()  # the nightly scan: classified records are left out
		queue = review.overview()
		assert all(r["item_id"] != b for r in queue["rows"])

	def test_a_record_cannot_be_classified_above_its_file(self):
		a = self.item(5)
		frappe.get_doc(
			{
				"doctype": "RD File",
				"file_number": "RDGAPSTEST-1",
				"subject": "A file",
				"records": [{"item": a}],
			}
		).insert(ignore_permissions=True)
		assert register.files_below([a], 1, self.DEPT) == 1
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "RD Item Scope",
					"item": a,
					"classification": "Restricted",
					"department": self.DEPT,
				}
			).insert(ignore_permissions=True)
		assert register.files_below([a], 0, None) == 0
