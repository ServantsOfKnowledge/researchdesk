"""Integration tests for joining the portal from its own page. Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_signup
"""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import access, signup
from sok_resdesk.core import access as core

EMAIL = "rd-join-test@example.org"


class TestJoin(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.saved = frappe.get_single("RD Settings").reader_signup

	def setUp(self):
		self.clean()
		self.mode(core.SIGNUP_OPEN)
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")
		self.clean()
		self.mode(self.saved)

	def clean(self):
		frappe.db.delete("RD Reader Request", {"email": EMAIL})
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)

	def mode(self, value):
		user = frappe.session.user
		frappe.set_user("Administrator")
		doc = frappe.get_single("RD Settings")
		doc.reader_signup = value
		doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")
		frappe.set_user(user)

	def test_open_signup_makes_a_reader_who_can_read_at_once_without_an_email(self):
		queued = frappe.db.count("Email Queue")
		out = signup.join(full_name="Asha", email=EMAIL, password="longenough1")
		self.assertEqual(out["status"], "member")
		self.assertEqual(out["next"], signup.main_page())  # no page asked for: the main page
		user = frappe.get_doc("User", EMAIL)
		self.assertTrue(user.enabled)
		self.assertIn(access.READER_ROLE, [r.role for r in user.roles])
		self.assertEqual(frappe.db.count("Email Queue"), queued)  # nothing waits on email
		from frappe.utils.password import check_password

		self.assertEqual(check_password(EMAIL, "longenough1"), EMAIL)

	def test_a_reader_goes_back_to_the_book_they_came_from_but_never_elsewhere(self):
		out = signup.join(full_name="Asha", email=EMAIL, password="longenough1", next="/library/item/abc")
		self.assertEqual(out["next"], "/library/item/abc")
		self.clean()
		out = signup.join(full_name="Asha", email=EMAIL, password="longenough1", next="//evil.example")
		self.assertEqual(out["next"], signup.main_page())

	def test_a_person_waiting_for_approval_goes_to_the_main_page_not_the_members_only_book(self):
		self.mode(core.SIGNUP_APPROVE)
		out = signup.join(full_name="Asha", email=EMAIL, password="longenough1", next="/library/item/abc")
		self.assertEqual(out["next"], signup.main_page())

	def test_approval_mode_makes_a_visitor_with_a_request_for_a_librarian(self):
		self.mode(core.SIGNUP_APPROVE)
		out = signup.join(full_name="Asha", email=EMAIL, password="longenough1")
		self.assertEqual(out["status"], "pending")
		self.assertEqual(out["next"], signup.main_page())
		self.assertNotIn(access.READER_ROLE, [r.role for r in frappe.get_doc("User", EMAIL).roles])
		self.assertEqual(frappe.db.get_value("RD Reader Request", {"user": EMAIL}, "status"), "Pending")

	def test_a_library_that_adds_its_readers_has_no_join(self):
		self.mode(core.SIGNUP_CLOSED)
		self.assertFalse(signup.open_to_join())
		with self.assertRaises(frappe.ValidationError):
			signup.join(full_name="Asha", email=EMAIL, password="longenough1")
		self.assertFalse(frappe.db.exists("User", EMAIL))

	def test_the_same_email_twice_and_a_short_password_are_refused(self):
		signup.join(full_name="Asha", email=EMAIL, password="longenough1")
		with self.assertRaises(frappe.ValidationError):
			signup.join(full_name="Asha again", email=EMAIL, password="longenough1")
		self.clean()
		with self.assertRaises(frappe.ValidationError):
			signup.join(full_name="Asha", email=EMAIL, password="short")
		self.assertFalse(frappe.db.exists("User", EMAIL))

	def test_a_robot_gets_thanks_and_no_account(self):
		out = signup.join(full_name="Bot", email=EMAIL, password="longenough1", rd_hp="http://spam")
		self.assertEqual(out["joined"], 1)
		self.assertFalse(frappe.db.exists("User", EMAIL))


class TestCanOpenDesk(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_no_administrator_yes(self):
		frappe.set_user("Guest")
		self.assertFalse(access.can_open_desk())
		frappe.set_user("Administrator")
		self.assertTrue(access.can_open_desk())
