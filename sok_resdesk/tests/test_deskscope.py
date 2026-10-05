"""0.43: staff see Research Desk in the Desk, not Frappe's own workspaces."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import deskscope

EMAIL = "rdtest-deskscope@example.org"


class TestDeskScope(IntegrationTestCase):
	def setUp(self):
		self.was = deskscope.scope()
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		self.set_scope(self.was)  # the accounts follow the setting back
		frappe.db.commit()

	def set_scope(self, value):
		s = frappe.get_single("RD Settings")
		s.desk_scope = value
		s.save(ignore_permissions=True)

	def user(self, *roles):
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL,
				"first_name": "Rdtest",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)

	def blocked(self):
		return {r.module for r in frappe.get_doc("User", EMAIL).block_modules}

	def test_staff_see_only_research_desk(self):
		self.set_scope(deskscope.EVERYONE)
		u = self.user("ResDesk Cataloguer")
		self.assertEqual(u.module_profile, deskscope.PROFILE)
		self.assertIn("Core", self.blocked())
		self.assertNotIn("ResDesk", self.blocked())
		self.assertEqual(u.default_workspace, "Research Desk")

	def test_system_managers_follow_the_setting(self):
		self.set_scope(deskscope.EVERYONE)
		self.user("System Manager")
		self.assertIn("Core", self.blocked())
		self.set_scope(deskscope.STAFF)  # changing the setting updates the accounts
		self.assertEqual(frappe.db.get_value("User", EMAIL, "module_profile"), None)
		self.assertEqual(self.blocked(), set())
		self.set_scope(deskscope.OFF)
		self.user("ResDesk Manager")
		self.assertEqual(self.blocked(), set())

	def test_administrator_and_readers_are_left_alone(self):
		self.set_scope(deskscope.EVERYONE)
		self.assertFalse(deskscope.applies_to(frappe.get_doc("User", "Administrator")))
		self.assertFalse(deskscope.applies_to(frappe._dict(name="r@x", user_type="Website User", roles=[])))

	def test_the_apps_screen_shows_research_desk(self):
		from frappe.boot import get_bootinfo

		self.set_scope(deskscope.EVERYONE)
		self.user("ResDesk Manager", "System Manager")
		frappe.set_user(EMAIL)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.clear_cache(user=EMAIL)
		boot = get_bootinfo()
		self.assertEqual([i.label for i in boot.desktop_icons], ["Research Desk"])
		self.assertIn("research desk", boot.workspace_sidebar_item)
		self.assertFalse({"build", "users", "website", "integrations"} & set(boot.workspace_sidebar_item))
		frappe.set_user("Administrator")
		frappe.clear_cache(user="Administrator")
		self.assertIn("Build", [i.label for i in get_bootinfo().desktop_icons])

	def test_everyone_includes_administrator_and_closes_frappes_desktop(self):
		from frappe.boot import get_bootinfo

		self.set_scope(deskscope.ALL)
		frappe.set_user("Administrator")
		frappe.clear_cache(user="Administrator")
		boot = get_bootinfo()
		self.assertEqual([i.label for i in boot.desktop_icons], ["Research Desk"])
		self.assertTrue(boot.get("resdesk_desk_only"))
		self.assertFalse(
			{"build", "users", "website", "integrations", "system"} & set(boot.workspace_sidebar_item)
		)
		# a library that keeps Administrator out of the scope still gets Frappe's desktop for it
		self.set_scope(deskscope.EVERYONE)
		frappe.clear_cache(user="Administrator")
		boot = get_bootinfo()
		self.assertFalse(boot.get("resdesk_desk_only"))
		self.assertIn("Framework", [i.label for i in boot.desktop_icons])
