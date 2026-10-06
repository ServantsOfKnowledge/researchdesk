"""0.65.1: transient database refusals (error 1020, deadlocks) are tried again from a fresh snapshot."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import dbretry


class TestDbRetry(IntegrationTestCase):
	def test_a_snapshot_conflict_is_tried_again(self):
		calls = []

		def work():
			calls.append(1)
			if len(calls) == 1:
				raise frappe.QueryDeadlockError(
					"(1020, \"Record has changed since last read in table 'tabRD Item'\")"
				)
			return "done"

		self.assertEqual(dbretry.run(work, pause=0), "done")
		self.assertEqual(len(calls), 2)

	def test_it_gives_up_after_the_attempts(self):
		calls = []

		def work():
			calls.append(1)
			raise frappe.QueryDeadlockError("(1213, 'Deadlock found')")

		with self.assertRaises(frappe.QueryDeadlockError):
			dbretry.run(work, attempts=3, pause=0)
		self.assertEqual(len(calls), 3)

	def test_other_errors_are_not_hidden(self):
		calls = []

		def work():
			calls.append(1)
			raise ValueError("a real mistake")

		with self.assertRaises(ValueError):
			dbretry.run(work, pause=0)
		self.assertEqual(len(calls), 1)
