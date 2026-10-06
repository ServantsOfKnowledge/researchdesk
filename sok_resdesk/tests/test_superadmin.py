"""0.65.1: a super admin for Servants of Knowledge; librarians with the manager role cannot change
the installation's own settings, the Server page or who holds the installation's roles."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import access, people, server

LIBRARIAN = "rdtest-librarian@example.org"
SUPER = "rdtest-super@example.org"
OTHER = "rdtest-other@example.org"


def _user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	return frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Rdtest",
			"send_welcome_email": 0,
			"roles": [{"role": r} for r in roles],
		}
	).insert(ignore_permissions=True)


class TestSuperAdmin(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_user(LIBRARIAN, ["ResDesk Manager"])
		_user(SUPER, ["SOK Super Admin"])
		_user(OTHER, ["ResDesk Cataloguer"])
		s = frappe.get_single("RD Settings")
		s.guest_access = "Records only"
		s.portal_title = "Rdtest Library"
		s.save()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		for email in (LIBRARIAN, SUPER, OTHER):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_role_exists_and_works_in_the_desk(self):
		role = frappe.get_doc("Role", "SOK Super Admin")
		self.assertEqual(role.desk_access, 1)
		self.assertTrue(access.is_super_admin(SUPER))
		self.assertFalse(access.is_super_admin(LIBRARIAN))
		self.assertTrue(access.is_staff(SUPER))

	def test_a_librarian_can_edit_the_libraries_own_settings_but_not_the_installations(self):
		frappe.set_user(LIBRARIAN)
		s = frappe.get_single("RD Settings")
		s.portal_title = "Rdtest Renamed"
		s.guest_access = "Login required"
		s.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_single_value("RD Settings", "portal_title"), "Rdtest Renamed")
		self.assertEqual(frappe.db.get_single_value("RD Settings", "guest_access"), "Records only")

	def test_the_super_admin_can_change_the_installation_settings(self):
		frappe.set_user(SUPER)
		s = frappe.get_single("RD Settings")
		s.guest_access = "Login required"
		s.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_single_value("RD Settings", "guest_access"), "Login required")

	def test_the_server_page_actions_are_the_super_admins(self):
		self.assertIn("SOK Super Admin", server.ADMINS)
		frappe.set_user(LIBRARIAN)
		with self.assertRaises(frappe.PermissionError):
			server.request_task("restart", {"service": "web"})
		with self.assertRaises(frappe.PermissionError):
			from sok_resdesk import features

			features.switch_on("notes")

	def test_a_librarian_cannot_hand_out_or_change_the_installations_roles(self):
		frappe.set_user(LIBRARIAN)
		with self.assertRaises(frappe.PermissionError):
			people.set_role(OTHER, "SOK Super Admin", 1)
		with self.assertRaises(frappe.PermissionError):
			people.set_role(OTHER, "System Manager", 1)
		with self.assertRaises(frappe.PermissionError):
			people.set_role(SUPER, "ResDesk Manager", 1)
		with self.assertRaises(frappe.PermissionError):
			people.set_enabled(SUPER, 0)
		self.assertNotIn("SOK Super Admin", people.managed_roles())
		people.set_role(OTHER, "ResDesk Proofreader", 1)  # their own roles still work

	def test_the_super_admin_can_give_the_role(self):
		frappe.set_user(SUPER)
		self.assertIn("SOK Super Admin", people.managed_roles())
		people.set_role(OTHER, "SOK Super Admin", 1)
		self.assertTrue(access.is_super_admin(OTHER))
