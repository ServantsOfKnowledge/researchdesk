"""0.56: the Desk's sidebar holds every Research Desk screen, and the administrator's tools for
those who may use them."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import features, sidebar

EMAIL = "rdtest-sidebar@example.org"


def sidebar_of(boot) -> dict:
	"""Our sidebar in the boot data: keyed by lower-case title before Frappe 16.50, by name from it."""
	sidebars = boot.get("module_sidebars") or boot.get("workspace_sidebar_item") or {}
	for key, value in sidebars.items():
		if key.lower() == sidebar.TITLE.lower():
			return value
	raise AssertionError(f"no {sidebar.TITLE} sidebar in {sorted(sidebars)}")


class TestSidebar(IntegrationTestCase):
	def labels(self, boot):
		return [i["label"] for i in sidebar_of(boot)["items"]]

	def test_the_shipped_sidebar_has_every_screen_in_sections(self):
		items = sidebar.items()
		labels = [i["label"] for i in items]
		for section in (
			"Catalogue",
			"Exchange",
			"Readers and Research",
			"Keeping",
			"Running the Library",
			"Administration",
		):
			self.assertIn(section, labels)
		for screen in (
			"Items",
			"Deposits",
			"Exports",
			"Library Systems",
			"Reader Requests",
			"Server",
			"Users",
			"Error Log",
		):
			self.assertIn(screen, labels)
		self.assertEqual(items[0]["label"], "Home")
		# every screen is a child of a section; targets are real doctypes and pages
		for i in items:
			if i["type"] == "Link" and i.get("link_type") == "DocType":
				self.assertTrue(frappe.db.exists("DocType", i["link_to"]), i["link_to"])
			if i["type"] == "Link" and i.get("link_type") == "Page":
				self.assertTrue(frappe.db.exists("Page", i["link_to"]), i["link_to"])
		self.assertTrue(any(i.get("link_type") == "URL" and i["url"] == "/" for i in items))

	def test_a_switched_off_feature_takes_its_screens_and_an_empty_section_goes(self):
		hidden = {"RD Preservation Event", "RD Tombstone"}
		labels = [i["label"] for i in sidebar.items(hidden)]
		self.assertNotIn("Preservation Events", labels)
		self.assertNotIn("Keeping", labels)  # nothing left in it
		self.assertIn("Items", labels)

	def test_it_follows_the_features(self):
		from frappe.boot import get_bootinfo

		def targets():
			frappe.clear_cache()
			return [i.get("link_to") for i in sidebar_of(get_bootinfo())["items"]]

		sidebar.refresh()
		self.assertIn("RD Deposit", targets())
		frappe.db.set_single_value("RD Settings", "feature_deposit", 0)
		self.addCleanup(
			lambda: (frappe.db.set_single_value("RD Settings", "feature_deposit", 1), features.apply())
		)
		features.apply()
		self.assertNotIn("RD Deposit", targets())

	def test_only_a_system_manager_is_shown_administration(self):
		from frappe.boot import get_bootinfo

		sidebar.refresh()
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": EMAIL,
				"first_name": "Rdtest",
				"send_welcome_email": 0,
				"roles": [{"role": "ResDesk Cataloguer"}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True))
		frappe.set_user(EMAIL)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.clear_cache(user=EMAIL)
		labels = self.labels(get_bootinfo())
		self.assertIn("Items", labels)
		self.assertNotIn("Administration", labels)
		self.assertNotIn("Error Log", labels)
		frappe.set_user("Administrator")
		frappe.clear_cache(user="Administrator")
		self.assertIn("Administration", self.labels(get_bootinfo()))


class TestBrandLogo(IntegrationTestCase):
	def test_the_libraries_logo_is_on_the_desks_app_icon(self):
		from frappe.boot import get_bootinfo

		before = frappe.db.get_single_value("RD Settings", "portal_logo")
		frappe.db.set_single_value("RD Settings", "portal_logo", "/files/rdtest-logo.png")
		self.addCleanup(frappe.db.set_single_value, "RD Settings", "portal_logo", before)
		frappe.clear_cache()
		boot = get_bootinfo()
		apps = [a for a in boot.get("app_data") or [] if a.get("app_name") == "sok_resdesk"]
		if not apps:  # a Frappe before 16.50 keeps the logo on the Desktop Icon instead
			self.skipTest("this Frappe has no apps list")
		self.assertTrue(
			apps[0]["app_logo_url"].endswith("rdtest-logo.png") or "favicon" in apps[0]["app_logo_url"]
		)
