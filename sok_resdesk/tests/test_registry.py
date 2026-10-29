"""The install note: when it may be sent, what is kept when one is received. Needs a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_registry
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import registry
from sok_resdesk.core import registry as rules

ID = "123e4567-e89b-42d3-a456-426614174000"


def reset_last_sent(value):
	"""Put the last-sent time back as it was; an unset one is removed, not written as an empty date."""
	if value is None:
		frappe.db.sql("delete from tabSingles where doctype='RD Settings' and field='registry_last_sent'")
	else:
		frappe.db.set_single_value("RD Settings", "registry_last_sent", value)
	frappe.clear_cache(doctype="RD Settings")


class TestInstallNote(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.was = frappe.db.get_single_value("RD Settings", "share_install_info", cache=False)
		self.last = frappe.db.get_single_value("RD Settings", "registry_last_sent", cache=False)
		reset_last_sent(self.last)
		frappe.db.delete("RD Install Ping", {"name": ID})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("RD Settings", "share_install_info", self.was or 0)
		reset_last_sent(self.last)
		frappe.db.delete("RD Install Ping", {"name": ID})
		frappe.conf.pop("resdesk_classified", None)
		frappe.db.commit()

	def test_nothing_is_sent_unless_the_library_said_yes(self):
		frappe.db.set_single_value("RD Settings", "share_install_info", 0)
		with mock.patch("requests.post") as post:
			out = registry.send()
		self.assertEqual(out["sent"], 0)
		post.assert_not_called()

	def test_a_classified_site_never_sends_even_when_ticked(self):
		frappe.db.set_single_value("RD Settings", "share_install_info", 1)
		frappe.conf.resdesk_classified = 1
		with mock.patch("requests.post") as post:
			self.assertEqual(registry.send()["sent"], 0)
		post.assert_not_called()

	def test_a_note_is_sent_once_and_what_was_sent_is_kept_to_show(self):
		frappe.db.set_single_value("RD Settings", "share_install_info", 1)
		with mock.patch("requests.post") as post:
			post.return_value.status_code = 200
			self.assertEqual(registry.send()["sent"], 1)
			body = post.call_args.kwargs["json"]
			self.assertEqual(set(body), {"id", "version", "edition", "kind", "profiles"})
			self.assertEqual(post.call_args.args[0], rules.ENDPOINT)
			registry.daily()  # not due again for four weeks
			self.assertEqual(post.call_count, 1)
		self.assertNotEqual(
			frappe.db.get_single_value("RD Settings", "registry_last_sent", cache=False), self.last
		)
		self.assertIn(
			body["id"], frappe.db.get_single_value("RD Settings", "registry_last_note", cache=False)
		)
		self.assertEqual(registry.instance_id(), body["id"])  # the same id every time

	def test_a_failed_send_is_tried_again_later(self):
		import requests

		frappe.db.set_single_value("RD Settings", "share_install_info", 1)
		with mock.patch("requests.post", side_effect=requests.ConnectionError):
			self.assertEqual(registry.send()["sent"], 0)
		self.assertEqual(
			frappe.db.get_single_value("RD Settings", "registry_last_sent", cache=False), self.last
		)

	def test_a_received_note_keeps_one_record_per_id_and_no_address(self):
		note = rules.payload(ID, "0.109.0", "standard", "docker", ["school"])
		registry.take(note)
		registry.take(note)  # within the hour: nothing changes
		row = frappe.get_doc("RD Install Ping", ID)
		self.assertEqual((row.version, row.profiles, row.pings), ("0.109.0", "school", 1))
		fields = {f.fieldname for f in frappe.get_meta("RD Install Ping").fields}
		self.assertFalse(fields & {"ip", "ip_address", "domain", "site", "name_of_library"})
		frappe.db.set_value("RD Install Ping", ID, "last_seen", "2020-01-01 00:00:00")
		registry.take({**note, "version": "0.110.0"})
		row.reload()
		self.assertEqual((row.version, row.pings), ("0.110.0", 2))

	def test_a_site_that_is_not_the_registry_answers_as_if_the_page_did_not_exist(self):
		frappe.db.set_single_value("RD Settings", "registry_receive", 0)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.DoesNotExistError):
			registry.ping()
