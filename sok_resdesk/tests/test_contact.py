"""Integration tests for messages from visitors (RD Message, the Contact us form). Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_contact
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime
from frappe.utils.password import set_encrypted_password

from sok_resdesk import contact


class TestContact(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.settings = frappe.get_single("RD Settings")
		cls.saved = {
			k: cls.settings.get(k) for k in ("contact_enabled", "contact_keep_days", "telegram_chat_id")
		}

	def setUp(self):
		frappe.db.delete("RD Message")
		self.set_up_settings(contact_enabled=1, contact_keep_days=365, telegram_chat_id="")
		self.posts = []
		self._post = contact.requests.post
		contact.requests.post = lambda url, **kw: (
			self.posts.append((url, kw)) or type("R", (), {"status_code": 200})()
		)

	def tearDown(self):
		contact.requests.post = self._post
		frappe.db.delete("RD Message")
		self.set_up_settings(**self.saved)

	def set_up_settings(self, **values):
		doc = frappe.get_single("RD Settings")
		doc.update(values)
		doc.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")

	def test_a_message_is_kept_as_new(self):
		self.assertEqual(
			contact.send(message="Is volume two of this book held?", full_name="Asha"), {"sent": 1}
		)
		row = frappe.get_last_doc("RD Message")
		self.assertEqual((row.status, row.full_name), ("New", "Asha"))

	def test_a_robot_gets_thanks_and_nothing_is_kept(self):
		self.assertEqual(contact.send(message="A fine message here.", rd_hp="http://spam"), {"sent": 1})
		self.assertEqual(frappe.db.count("RD Message"), 0)

	def test_no_message_and_too_short_are_refused(self):
		for text in ("", "hi"):
			with self.assertRaises(frappe.ValidationError):
				contact.send(message=text)

	def test_switched_off_takes_nothing(self):
		self.set_up_settings(contact_enabled=0)
		with self.assertRaises(frappe.ValidationError):
			contact.send(message="Is anyone there? Hello.")

	def test_telegram_is_told_only_that_a_message_came(self):
		self.set_up_settings(telegram_chat_id="12345")
		set_encrypted_password("RD Settings", "RD Settings", "123:abc", "telegram_bot_token")
		contact.send(message="My private words about page nine.")
		contact.tell_telegram(frappe.get_last_doc("RD Message").name)
		self.assertEqual(len(self.posts), 1)
		url, kw = self.posts[0]
		self.assertIn("/bot123:abc/sendMessage", url)
		self.assertNotIn("private words", kw["json"]["text"])
		self.assertEqual(kw["json"]["chat_id"], "12345")

	def test_without_a_token_telegram_is_not_called(self):
		contact.send(message="Nothing set up, so nothing sent.")
		contact.tell_telegram(frappe.get_last_doc("RD Message").name)
		self.assertEqual(self.posts, [])

	def test_old_messages_are_deleted_and_zero_keeps_all(self):
		contact.send(message="An old message about a book.")
		name = frappe.get_last_doc("RD Message").name
		frappe.db.set_value(
			"RD Message", name, "creation", add_days(now_datetime(), -400), update_modified=False
		)
		self.set_up_settings(contact_keep_days=0)
		self.assertEqual(contact.purge_old(), 0)
		self.set_up_settings(contact_keep_days=365)
		self.assertEqual(contact.purge_old(), 1)
		self.assertFalse(frappe.db.exists("RD Message", name))
