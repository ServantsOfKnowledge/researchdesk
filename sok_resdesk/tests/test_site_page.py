"""Integration tests for the organisation's own pages (RD Site Page, /p/<address>). Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_site_page
"""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import sitepages


def top_bar():
	return [i.url for i in frappe.get_single("Website Settings").top_bar_items]


class TestSitePage(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("RD Site Page", pluck="name"):
			frappe.delete_doc("RD Site Page", name, force=True)
		frappe.db.commit()

	def make(self, **values):
		doc = frappe.get_doc({"doctype": "RD Site Page", "title": "Join Us", "published": 1, **values})
		doc.insert(ignore_permissions=True)
		return doc

	def test_address_comes_from_the_title(self):
		self.assertEqual(self.make().name, "join-us")

	def test_guests_see_only_published_pages(self):
		self.make(title="Draft", published=0)
		self.make(title="Live")
		frappe.set_user("Guest")
		self.assertIsNone(sitepages.get("draft"))
		self.assertEqual(sitepages.get("live").title, "Live")

	def test_members_only_needs_a_reader_not_just_a_login(self):
		from sok_resdesk import access

		self.make(members_only=1)
		frappe.set_user("Guest")
		self.assertFalse(access.is_member())

	def test_top_bar_link_comes_and_goes(self):
		doc = self.make(in_menu=1, menu_label="Take part")
		self.assertIn("/p/join-us", top_bar())
		doc.published = 0
		doc.save(ignore_permissions=True)
		self.assertNotIn("/p/join-us", top_bar())

	def test_members_only_page_is_not_in_the_top_bar(self):
		doc = self.make(in_menu=1, members_only=1)
		self.assertEqual(doc.in_menu, 0)
		self.assertNotIn("/p/join-us", top_bar())
