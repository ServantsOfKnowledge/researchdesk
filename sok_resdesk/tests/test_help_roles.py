"""Desk help follows the person's roles. Needs a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_help_roles
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import help as rd_help
from sok_resdesk.core import helpdocs


def slugs(page):
	return [p["slug"] for g in page["index"] for p in g["pages"]]


class TestHelpByRole(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def as_roles(self, *roles):
		return mock.patch.object(rd_help, "_my_tracks", lambda: helpdocs.tracks_for(roles))

	def test_start_here_names_the_jobs_the_roles_give(self):
		with self.as_roles("ResDesk Cataloguer"):
			page = rd_help.get_page()
		self.assertEqual(page["slug"], "start")
		self.assertIn("Cataloguing and collections", page["html"])
		self.assertIn("Lending and acquisitions", page["html"])
		self.assertNotIn("Technical reference", page["html"])

	def test_the_navigation_is_trimmed_to_the_role_and_show_all_brings_the_rest_back(self):
		with self.as_roles("ResDesk Cataloguer"):
			mine = rd_help.get_page("ingesting")
			everything = rd_help.get_page("ingesting", all=1)
		self.assertIn("ingesting", slugs(mine))
		self.assertNotIn("api", slugs(mine))
		self.assertFalse(mine["show_all"])
		self.assertIn("api", slugs(everything))
		self.assertTrue(everything["show_all"])

	def test_a_page_outside_the_role_still_opens_and_shows_the_whole_list(self):
		with self.as_roles("ResDesk Cataloguer"):
			page = rd_help.get_page("api")  # a link from elsewhere
		self.assertEqual(page["slug"], "api")
		self.assertTrue(page["show_all"])
		self.assertIn("api", slugs(page))

	def test_an_unknown_page_is_still_refused(self):
		with self.assertRaises(frappe.DoesNotExistError):
			rd_help.get_page("no-such-page")
