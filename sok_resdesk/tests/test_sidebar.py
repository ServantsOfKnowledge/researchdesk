"""0.56: the Desk's sidebar holds every Research Desk screen, and the administrator's tools for
those who may use them."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import features, sidebar

EMAIL = "rdtest-sidebar@example.org"


class TestSidebar(IntegrationTestCase):
	def labels(self, boot):
		return [i["label"] for i in boot.workspace_sidebar_item[sidebar.TITLE.lower()]["items"]]

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

	def test_it_is_kept_in_the_database_and_follows_the_features(self):
		sidebar.refresh()
		doc = frappe.get_doc("Workspace Sidebar", sidebar.TITLE)
		self.assertEqual((doc.module, doc.standard), ("ResDesk", 0))
		self.assertIn("RD Deposit", [i.link_to for i in doc.items])
		frappe.db.set_single_value("RD Settings", "feature_deposit", 0)
		self.addCleanup(
			lambda: (frappe.db.set_single_value("RD Settings", "feature_deposit", 1), features.apply())
		)
		features.apply()
		self.assertNotIn(
			"RD Deposit", [i.link_to for i in frappe.get_doc("Workspace Sidebar", sidebar.TITLE).items]
		)

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
