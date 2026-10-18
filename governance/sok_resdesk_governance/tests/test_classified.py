"""0.79: classified mode refuses outside web requests and keeps its settings."""

import frappe
import requests
from frappe.tests import IntegrationTestCase

from sok_resdesk_governance import classified


class TestClassified(IntegrationTestCase):
	def setUp(self):
		self.was = frappe.conf.get("resdesk_classified")
		frappe.conf.resdesk_classified = 1
		self.addCleanup(self._clean)

	def _clean(self):
		classified.remove_guard()
		if self.was is None:
			frappe.conf.pop("resdesk_classified", None)
		else:
			frappe.conf.resdesk_classified = self.was

	def test_an_outside_address_is_refused_and_the_machine_itself_is_not(self):
		classified.install_guard()
		with self.assertRaises(classified.ClassifiedModeError):
			requests.get("http://archive.example.invalid/")
		with self.assertRaises(requests.exceptions.ConnectionError):  # allowed through; nothing listens
			requests.get("http://localhost:9/", timeout=2)

	def test_outgoing_mail_to_an_outside_server_is_refused(self):
		import smtplib

		classified.install_guard()
		with self.assertRaises(classified.ClassifiedModeError):
			smtplib.SMTP("smtp.example.invalid", 25, timeout=2)

	def test_another_site_that_is_not_classified_is_not_bound(self):
		classified.install_guard()
		frappe.conf.pop(
			"resdesk_classified"
		)  # the guard stays installed in the process, the check is per call
		with self.assertRaises(requests.exceptions.ConnectionError):
			requests.get("http://localhost:9/", timeout=2)
		classified._refuse("archive.example.invalid")  # not classified here: no refusal

	def test_a_request_error_handler_catches_the_refusal(self):
		classified.install_guard()
		try:
			requests.get("http://archive.example.invalid/")
		except requests.RequestException as e:
			self.assertIn("Classified mode", str(e))

	def test_the_settings_form_cannot_switch_the_limits_off(self):
		doc = frappe.get_doc("RD Settings")
		doc.governance, doc.guest_access, doc.feature_sharing = 0, "Each item's setting", 1
		classified.enforce(doc)
		self.assertEqual((doc.governance, doc.guest_access, doc.feature_sharing), (1, "Login required", 0))

	def test_a_search_is_logged_without_its_words(self):
		from unittest import mock

		from sok_resdesk_governance import audit

		with mock.patch("sok_resdesk_governance.audit.record") as record:
			audit.sink("search", "", "books: secret plan")
			record.assert_called_with("search", "", "books")
			frappe.conf.pop("resdesk_classified")
			audit.sink("search", "", "books: plan")
			record.assert_called_with("search", "", "books: plan")
