"""The Desk's numbers come from the last count at once, and a newer one is counted in the background. Need a
site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_dashboard
"""

import time

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import dashboard


class TestDashboardCache(IntegrationTestCase):
	def setUp(self):
		self.queued = []
		self._enqueue = frappe.enqueue
		frappe.enqueue = lambda *a, **k: self.queued.append((a, k))

	def tearDown(self):
		frappe.enqueue = self._enqueue
		frappe.cache.delete_value(dashboard.CACHE_KEY)

	def test_a_fresh_count_is_returned_as_it_is_and_nothing_is_queued(self):
		first = dashboard.numbers(refresh=1)
		again = dashboard.numbers()
		self.assertEqual(first["at"], again["at"])
		self.assertEqual(self.queued, [])

	def test_an_old_count_is_returned_at_once_and_a_new_one_is_queued(self):
		old = dashboard.rebuild()
		old["at"] = time.time() - dashboard.FRESH_SECONDS - 5
		frappe.cache.set_value(dashboard.CACHE_KEY, old)
		got = dashboard.numbers()
		self.assertEqual(got["at"], old["at"])
		self.assertEqual(len(self.queued), 1)
		self.assertEqual(self.queued[0][1]["job_id"], dashboard.JOB_ID)

	def test_with_nothing_kept_the_first_caller_waits_for_the_count(self):
		frappe.cache.delete_value(dashboard.CACHE_KEY)
		self.assertIn("groups", dashboard.numbers())
