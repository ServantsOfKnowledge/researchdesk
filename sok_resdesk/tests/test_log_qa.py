import json

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import __version__, server


class TestLogQA(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _entry(self, error):
		doc = frappe.get_doc({"doctype": "Error Log", "method": "qa-test", "error": error})
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_a_fixed_error_logged_before_the_fix_is_resolved_and_can_be_cleared(self):
		known = self._entry("Traceback\nKeyError: b'created_at'")
		odd = self._entry("Traceback\nValueError: something nobody has catalogued")
		# the fix became the installed version far in the future: everything logged now predates it
		frappe.db.set_default(server.HISTORY_KEY, json.dumps([[__version__, "2999-01-01 00:00:00"]]))
		qa = server.log_qa()
		verdicts = {g["title"]: g["verdict"] for g in qa["groups"]}
		self.assertIn("resolved", verdicts.values())
		self.assertGreaterEqual(qa["unknown"]["count"], 1)
		self.assertGreaterEqual(qa["clearable"], 1)
		server.clear_resolved_errors()
		self.assertFalse(frappe.db.exists("Error Log", known))
		self.assertTrue(frappe.db.exists("Error Log", odd))  # not recognised: never cleared

	def test_an_error_after_the_fix_was_installed_is_recurring(self):
		self._entry("KeyError: b'created_at'")
		frappe.db.set_default(server.HISTORY_KEY, json.dumps([[__version__, "2000-01-01 00:00:00"]]))
		self.assertIn("recurring", {g["verdict"] for g in server.log_qa()["groups"]})

	def test_the_installed_version_is_recorded_once(self):
		frappe.db.set_default(server.HISTORY_KEY, "[]")
		server.record_version()
		server.record_version()
		self.assertEqual([v for v, _ts in server._version_history()], [__version__])
