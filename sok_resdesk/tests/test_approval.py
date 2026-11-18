"""Approval to read: found by all, read only by staff and readers a librarian approved."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from sok_resdesk import access, approval

ITEM = "rdtestapproval1"
READER = "rdtestapproval1@example.com"


class TestApproval(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._clean()
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": ITEM,
				"title": "A Restricted Thesis",
				"language": "eng",
				"published": 1,
				"visibility": "Approval to read",
			}
		).insert(ignore_permissions=True)
		access.add_reader(READER, "Test Reader", send_welcome=False)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		self._clean()

	def _clean(self):
		frappe.db.delete("RD Access Request", {"item": ITEM})
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.db.delete("Has Role", {"parent": READER})
		frappe.db.delete("User", {"name": READER})
		frappe.db.commit()

	def can_read(self):
		return access.can_read("Approval to read", item=ITEM)

	def test_a_reader_reads_only_once_approved_and_not_past_the_end_date(self):
		frappe.set_user(READER)
		self.assertTrue(access.can_find("Approval to read"))
		self.assertFalse(self.can_read())
		self.assertEqual(approval.request(ITEM, "my thesis")["status"], "Pending")
		self.assertEqual(approval.state(ITEM)["status"], "Pending")
		self.assertFalse(self.can_read())
		self.assertRaises(frappe.PermissionError, approval.decide, "[]", "Approved")  # a reader cannot decide
		frappe.set_user("Administrator")
		name = frappe.db.get_value("RD Access Request", {"item": ITEM, "user": READER})
		approval.decide([name], "Approved")
		frappe.set_user(READER)
		self.assertTrue(self.can_read())
		self.assertIn(ITEM, access.granted_items())
		self.assertEqual(access.search_filter("pages").count(ITEM), 1)  # its pages are searchable for them
		frappe.set_user("Administrator")
		frappe.db.set_value("RD Access Request", name, "valid_until", add_days(nowdate(), -1))
		frappe.set_user(READER)
		self.assertFalse(self.can_read())  # the approval ended
		self.assertEqual(approval.state(ITEM)["status"], "Expired")
		self.assertNotIn(ITEM, access.search_filter("pages"))

	def test_decline_withdraw_and_ask_again(self):
		frappe.set_user(READER)
		approval.request(ITEM)
		self.assertEqual(approval.withdraw(ITEM)["status"], "Withdrawn")
		approval.request(ITEM, "again")
		frappe.set_user("Administrator")
		name = frappe.db.get_value("RD Access Request", {"item": ITEM, "user": READER})
		approval.decide([name], "Declined", note="Not for undergraduates")
		frappe.set_user(READER)
		out = approval.state(ITEM)
		self.assertEqual((out["status"], out["note"]), ("Declined", "Not for undergraduates"))
		self.assertFalse(self.can_read())
		self.assertEqual(approval.request(ITEM, "I am a PhD student")["status"], "Pending")  # may ask again
		self.assertEqual(frappe.db.count("RD Access Request", {"item": ITEM}), 1)

	def test_staff_read_without_a_request_and_other_books_do_not_need_one(self):
		self.assertTrue(self.can_read())  # Administrator
		frappe.set_user("Guest")
		self.assertFalse(self.can_read())
		self.assertTrue(access.can_find("Approval to read"))
		frappe.set_user(READER)
		self.assertRaises(frappe.DoesNotExistError, approval.request, "no-such-book")
