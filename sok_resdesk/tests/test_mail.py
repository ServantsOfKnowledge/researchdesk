import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import mail


class TestMail(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_save_makes_the_default_outgoing_account(self):
		mail.save("library@example.org", "smtp.example.org", 587, "", "secret-pass", "tls")
		self.assertEqual(mail.outgoing_account(), "Research Desk")
		doc = frappe.get_doc("Email Account", "Research Desk")
		self.assertTrue(doc.enable_outgoing and doc.default_outgoing and doc.use_tls)
		mail.save("library@example.org", "smtp.example.org", 465, "", "", "ssl")  # keeps the password
		doc.reload()
		self.assertEqual(doc.smtp_port, 465)
		self.assertTrue(doc.use_ssl_for_outgoing and not doc.use_tls)

	def test_a_bad_form_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			mail.save("not-an-address", "smtp.example.org", 587, "", "x", "tls")

	def test_status_and_health_name_missing_email(self):
		frappe.db.set_value("Email Account", {"enable_outgoing": 1}, "enable_outgoing", 0)
		self.assertFalse(mail.status()["ready"])
		from sok_resdesk import server

		self.assertEqual(server._mail_check()["state"] in ("warn", "bad"), True)
