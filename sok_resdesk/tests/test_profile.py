import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import profile


class TestProfile(IntegrationTestCase):
	def setUp(self):
		self.user = "rd-profile-test@example.org"
		if not frappe.db.exists("User", self.user):
			frappe.get_doc(
				{"doctype": "User", "email": self.user, "first_name": "Profile", "send_welcome_email": 0}
			).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_person_saves_and_reads_their_profile(self):
		frappe.set_user(self.user)
		self.assertFalse(profile.has_profile())
		profile.save(
			kind="Organisation", organisation="Test Trust", wants_proofreader=1, access_need="Low vision"
		)
		self.assertTrue(profile.has_profile())
		mine = profile.mine()["profile"]
		self.assertEqual(mine["organisation"], "Test Trust")
		self.assertEqual(mine["wants_proofreader"], 1)
		self.assertEqual(mine["access_need"], "Low vision")
		profile.save(about="Hello")  # an edit keeps the rest
		self.assertEqual(profile.mine()["profile"]["organisation"], "Test Trust")

	def test_guests_cannot_and_support_details_stay_private(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			profile.save(about="x")
		frappe.set_user(self.user)
		profile.save(access_need="Blind")
		other = "rd-profile-other@example.org"
		if not frappe.db.exists("User", other):
			frappe.get_doc(
				{"doctype": "User", "email": other, "first_name": "Other", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(other)
		self.assertFalse(frappe.has_permission("RD Reader Profile", "read", self.user))

	def test_manager_grants_a_role(self):
		frappe.set_user("Administrator")
		profile.grant(self.user, "ResDesk Proofreader")
		self.assertIn("ResDesk Proofreader", frappe.get_roles(self.user))
		with self.assertRaises(frappe.ValidationError):
			profile.grant(self.user, "System Manager")
