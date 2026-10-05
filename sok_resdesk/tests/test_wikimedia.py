"""0.49: each person's own Wikimedia account. Wikimedia is stood in for; the doctype, the
permissions, the encrypted token and what is sent (and as whom) are real."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import contribute, wikimedia

WHO = {"name": "Volunteer", "id": 7, "rights": ["read", "edit", "createpage"], "groups": ["user"]}
TOKEN = "t" * 40


class TestWikimediaAccount(IntegrationTestCase):
	def setUp(self):
		self.user = frappe.session.user
		self.addCleanup(self._clean)
		self._clean()

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Wikimedia Account", {"name": "Administrator"})
		frappe.cache.delete_value(contribute.PLAN_KEY)
		frappe.db.commit()

	def connect(self, who=WHO, token=TOKEN):
		with mock.patch("sok_resdesk.core.wikimedia.WikimediaClient.whoami", return_value=who):
			return wikimedia.connect(token)

	def test_connecting_keeps_the_token_encrypted_and_private(self):
		self.assertFalse(wikimedia.status()["connected"])
		status = self.connect()
		self.assertEqual((status["connected"], status["wikimedia_user"]), (True, "Volunteer"))
		self.assertNotIn(TOKEN, str(status))  # never sent to the browser
		raw = frappe.db.get_value("RD Wikimedia Account", "Administrator", "token")
		self.assertNotEqual(raw, TOKEN)  # masked in the table, kept in the encrypted store
		self.assertEqual(wikimedia.token_for("Administrator"), TOKEN)
		self.assertNotIn(
			TOKEN, frappe.as_json(frappe.get_doc("RD Wikimedia Account", "Administrator").as_dict())
		)
		# connecting again replaces the token (a new consumer), still one record
		self.connect(token="n" * 40)
		self.assertEqual(wikimedia.token_for("Administrator"), "n" * 40)
		self.assertEqual(frappe.db.count("RD Wikimedia Account", {"name": "Administrator"}), 1)

	def test_a_token_that_cannot_edit_or_is_not_a_token_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "whole access token"):
			wikimedia.connect("short")
		with self.assertRaisesRegex(frappe.ValidationError, "not allowed to edit"):
			self.connect(who={**WHO, "rights": ["read"]})
		self.assertFalse(wikimedia.connected("Administrator"))
		from sok_resdesk.core.wikimedia import WikimediaError

		with mock.patch(
			"sok_resdesk.core.wikimedia.WikimediaClient.whoami", side_effect=WikimediaError("refused")
		):
			with self.assertRaisesRegex(frappe.ValidationError, "did not accept"):
				wikimedia.connect(TOKEN)

	def test_disconnect_forgets_the_token(self):
		self.connect()
		self.assertFalse(wikimedia.disconnect()["connected"])
		self.assertEqual(wikimedia.token_for("Administrator"), "")
		with self.assertRaisesRegex(frappe.ValidationError, "Connect your own Wikimedia account"):
			wikimedia.need_account("Administrator")

	def test_wikidata_edits_are_sent_as_the_person(self):
		edits = [{"qid": "Q1", "kind": "label", "lang": "kn", "value": "ಕನಕದಾಸ"}]
		frappe.cache.set_value(contribute.PLAN_KEY, {"edits": edits, "people": 1, "books": 0})
		with self.assertRaisesRegex(frappe.ValidationError, "Connect your own"):
			contribute.send_mine()  # not connected yet
		self.connect()
		sent = []

		class Client:
			def __init__(self, api, user, password, token="", **kw):
				self.token = token

			def login(self):
				return "Volunteer"

			def edit(self, qid, data, summary):
				sent.append((self.token, qid, data, summary))

		with mock.patch("sok_resdesk.core.push.WikidataClient", Client):
			result = contribute.run_send(as_user="Administrator")
		self.assertEqual(
			(result["by"], result["items"], result["edits"], result["failed"]), ("Volunteer", 1, 1, 0)
		)
		self.assertEqual(sent[0][0], TOKEN)  # their token: Wikidata credits them
		self.assertEqual(sent[0][2]["labels"]["kn"]["value"], "ಕನಕದಾಸ")
		self.assertTrue(frappe.db.get_value("RD Wikimedia Account", "Administrator", "last_used"))
		self.assertEqual(contribute.plan()["mine"], "Volunteer")

	def test_nobody_else_can_read_or_use_my_connection(self):
		self.connect()
		email = "rdtest-wikimedia@example.org"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Rdtest",
					"send_welcome_email": 0,
					"roles": [{"role": "ResDesk Cataloguer"}],
				}
			).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("User", email, force=True, ignore_permissions=True))
		frappe.set_user(email)
		try:
			doc = frappe.get_doc("RD Wikimedia Account", "Administrator")
			self.assertFalse(doc.has_permission("read"))  # another cataloguer: not theirs
			self.assertFalse(wikimedia.status()["connected"])  # their own status, not mine
			with self.assertRaisesRegex(frappe.ValidationError, "Connect your own"):
				wikimedia.need_account()
		finally:
			frappe.set_user("Administrator")
		# even someone allowed to read the record gets the token masked
		shown = frappe.client.get("RD Wikimedia Account", "Administrator")
		self.assertNotEqual(shown.get("token"), TOKEN)
