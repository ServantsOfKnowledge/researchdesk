"""A typed sentence read as search words and filters by the assistant."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import api

ITEM = "rdtestunderstand1"


class TestUnderstand(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": ITEM,
				"title": "Malegalalli Madumagalu",
				"language": "kan",
				"language_label": "Kannada",
				"published": 1,
				"visibility": "Public",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.delete("RD Item", {"name": ITEM})
		frappe.db.commit()

	def test_a_sentence_becomes_words_and_filters(self):
		reply = '{"query": "Kuvempu", "language": "Kannada", "year_from": 1950, "year_to": 1959}'
		q = "Kannada books by Kuvempu in the 1950s understandtest"
		with (
			mock.patch("sok_resdesk.assistant.enabled", return_value=True),
			mock.patch("sok_resdesk.assistant.ask", return_value=reply),
		):
			out = api.understand(q)
		# "understandtest" is a word typed, so a query of only Kuvempu is allowed (words may be dropped)
		self.assertEqual(out["q"], "Kuvempu")
		self.assertEqual(out["filters"]["language_label"], ["Kannada"])
		self.assertEqual((out["filters"]["year_from"], out["filters"]["year_to"]), (1950, 1959))

	def test_it_does_nothing_when_off_or_for_a_short_search(self):
		with mock.patch("sok_resdesk.assistant.enabled", return_value=False):
			self.assertEqual(api.understand("Kannada books by Kuvempu from 1950"), {})
		with mock.patch("sok_resdesk.assistant.enabled", return_value=True):
			self.assertEqual(api.understand("Kuvempu poems"), {})
