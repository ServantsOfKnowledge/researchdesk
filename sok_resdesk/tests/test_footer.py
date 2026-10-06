"""0.65.1: the portal footer reads 'Built on Frappe by ServantsOfKnowledge'."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk.resdesk.doctype.rd_settings.rd_settings import apply_branding


class TestFooter(IntegrationTestCase):
	def test_branding_sets_the_footer_line(self):
		apply_branding()
		line = frappe.db.get_single_value("Website Settings", "footer_powered")
		self.assertIn("Built on", line)
		self.assertIn(">Frappe</a>", line)
		self.assertIn("by <a", line)
		self.assertIn(">ServantsOfKnowledge</a>", line)
