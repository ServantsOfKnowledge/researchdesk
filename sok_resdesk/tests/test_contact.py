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
			k: cls.settings.get(k)
			for k in (
				"contact_enabled",
				"contact_keep_days",
				"telegram_chat_id",
				"guest_access",
				"telegram_username",
			)
		}

	def setUp(self):
		frappe.db.delete("RD Message")
		self.set_up_settings(contact_enabled=1, contact_keep_days=365, telegram_chat_id="")
		self.posts = []
		frappe.db.delete(
			"__Auth", {"doctype": "RD Settings", "name": "RD Settings", "fieldname": "telegram_bot_token"}
		)
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

	def test_a_guest_can_use_the_form_unless_the_library_asks_for_sign_in(self):
		frappe.set_user("Guest")
		try:
			self.assertTrue(contact.enabled())
			frappe.db.set_single_value("RD Settings", "guest_access", "Login required")
			frappe.clear_cache(doctype="RD Settings")
			self.assertFalse(contact.enabled())
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_single_value("RD Settings", "guest_access", self.saved["guest_access"])
			frappe.clear_cache(doctype="RD Settings")

	def test_the_public_telegram_name_is_saved_plain_or_refused(self):
		self.set_up_settings(telegram_username="https://t.me/SOKLibrary")
		self.assertEqual(frappe.get_single("RD Settings").telegram_username, "SOKLibrary")
		self.assertEqual(contact.public_telegram_link(), "https://t.me/SOKLibrary")
		with self.assertRaises(frappe.ValidationError):
			self.set_up_settings(telegram_username="+91 98765 43210")
		self.set_up_settings(telegram_username="")
		self.assertEqual(contact.public_telegram_link(), "")

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
		set_encrypted_password(
			"RD Settings", "RD Settings", "123456789:AAH-xyz_0123456789abcdefghijk", "telegram_bot_token"
		)
		contact.send(message="My private words about page nine.")
		contact.tell_telegram(frappe.get_last_doc("RD Message").name)
		self.assertEqual(len(self.posts), 1)
		url, kw = self.posts[0]
		self.assertIn("/bot123456789:AAH-xyz_0123456789abcdefghijk/sendMessage", url)
		self.assertNotIn("private words", kw["json"]["text"])
		self.assertEqual(kw["json"]["chat_id"], "12345")

	def test_the_test_button_reports_success_and_each_refusal_in_plain_words(self):
		self.set_up_settings(telegram_chat_id="12345")
		set_encrypted_password(
			"RD Settings", "RD Settings", "123456789:AAH-xyz_0123456789abcdefghijk", "telegram_bot_token"
		)
		self.assertTrue(contact.test_telegram()["ok"])
		contact.requests.post = lambda url, **kw: type(
			"R", (), {"status_code": 401, "json": lambda self: {"description": "Unauthorized"}}
		)()
		out = contact.test_telegram()
		self.assertFalse(out["ok"])
		self.assertIn("token", out["why"])
		self.assertNotIn("AAH-xyz", out["why"])
		self.assertTrue(contact.telegram_ready())

	def test_a_malformed_token_is_refused_before_any_request(self):
		self.set_up_settings(telegram_chat_id="12345")
		set_encrypted_password("RD Settings", "RD Settings", "bad/token?x", "telegram_bot_token")
		out = contact.test_telegram()
		self.assertFalse(out["ok"])
		self.assertIn("bot token", out["why"])
		self.assertEqual(self.posts, [])

	def test_finding_the_chat_id_lists_the_chats_or_says_to_write_to_the_bot(self):
		set_encrypted_password(
			"RD Settings", "RD Settings", "123456789:AAH-xyz_0123456789abcdefghijk", "telegram_bot_token"
		)
		answer = {
			"ok": True,
			"result": [
				{"update_id": 1, "message": {"chat": {"id": 42, "type": "private", "first_name": "Asha"}}}
			],
		}
		contact.requests.post = lambda url, **kw: type(
			"R", (), {"status_code": 200, "json": lambda self: answer}
		)()
		out = contact.find_telegram_chat()
		self.assertTrue(out["ok"])
		self.assertEqual(out["chats"][0]["id"], "42")
		answer["result"] = []
		out = contact.find_telegram_chat()
		self.assertFalse(out["ok"])
		self.assertIn("Start", out["why"])

	def test_the_test_button_says_when_nothing_is_set_up(self):
		self.assertFalse(contact.telegram_ready())
		self.assertFalse(contact.test_telegram()["ok"])

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
