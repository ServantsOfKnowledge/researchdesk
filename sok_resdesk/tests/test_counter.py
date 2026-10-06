"""0.65: the COUNTER style report over real page views."""

from datetime import date

import frappe

from sok_resdesk import counter
from sok_resdesk.tests.test_operations import OpsTestCase, _item


class TestCounter(OpsTestCase):
	def setUp(self):
		super().setUp()
		self.item = _item(91)
		frappe.db.set_value("RD Item", self.item, {"published": 1, "title": "Rdtest Counter Book"})
		frappe.db.sql("delete from `tabWeb Page View` where path like %s", f"%library/item/{self.item}%")
		for unique in ("1", "0", "0"):
			frappe.get_doc(
				{
					"doctype": "Web Page View",
					"path": f"library/item/{self.item}",
					"is_unique": unique,
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.sql("delete from `tabWeb Page View` where path like %s", f"%library/item/{self.item}%")
		frappe.db.commit()
		super().tearDown()

	def test_usage_rows_count_views_and_unique_visitors_per_book_and_month(self):
		today = frappe.utils.getdate()
		rows = counter.usage_rows(date(today.year, today.month, 1), today)
		mine = [r for r in rows if r[0] == self.item]
		self.assertEqual(len(mine), 1)
		self.assertEqual(mine[0][2:], (3, 1))

	def test_the_report_names_the_book_and_needs_a_manager(self):
		frappe.set_user("Administrator")
		today = frappe.utils.getdate()
		begin = f"{today.year}-{today.month:02d}"
		data = counter.report(begin_date=begin, end_date=begin)
		item = next(i for i in data["Report_Items"] if i["Title"] == "Rdtest Counter Book")
		counts = {x["Metric_Type"]: x["Count"] for x in item["Performance"][0]["Instance"]}
		self.assertEqual(counts, {"Total_Item_Investigations": 3, "Unique_Item_Investigations": 1})
		self.assertEqual(data["Report_Header"]["Report_ID"], "TR")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			counter.report()
		frappe.set_user("Administrator")

	def test_bad_dates_are_refused(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			counter.report(begin_date="soon")
		with self.assertRaises(frappe.ValidationError):
			counter.report(begin_date="2026-05", end_date="2026-01")
