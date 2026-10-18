"""0.80: the public mirror: what the main system may release, and what it takes back."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import outbound
from sok_resdesk_governance import mirror


class FakeMirror:
	def __init__(self):
		self.withdrawn = []

	def withdraw(self, item):
		self.withdrawn.append(item)


class TestMirror(IntegrationTestCase):
	TARGET = "rdmirrortest"

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.cache.delete_value("RD Settings")
		self.target = frappe.get_doc(
			{
				"doctype": "RD Push Target",
				"target_name": self.TARGET,
				"target_type": "Public mirror",
				"mirror_url": "https://mirror.example.org",
				"scope": "Everything",
				"enabled": 1,
				"dry_run": 0,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD External Record", {"target": self.TARGET})
		frappe.db.delete("RD Item Scope", {"item": ("like", "rdmirrortest%")})
		frappe.db.delete("RD Item", {"name": ("like", "rdmirrortest%")})
		frappe.delete_doc("RD Push Target", self.TARGET, force=True, ignore_permissions=True)
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.db.commit()

	def item(self, n, **values):
		return frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": f"rdmirrortest{n}",
				"title": f"Mirror {n}",
				"source": "Local",
				"published": 1,
				"visibility": "Public",
				"access_status": "Open",
				**values,
			}
		).insert(ignore_permissions=True)

	def test_only_a_public_open_published_local_book_is_releasable(self):
		a = self.item(1).name
		assert outbound.releasable(a)
		assert not outbound.releasable(self.item(2, visibility="Login to read").name)
		assert not outbound.releasable(self.item(3, published=0).name)
		assert not outbound.releasable(self.item(4, access_status="Restricted").name)
		assert not outbound.releasable(self.item(5, source="Internet Archive").name)
		assert not outbound.releasable("rdmirrortest-none")

	def test_a_classified_book_is_not_releasable_and_is_withdrawn(self):
		a = self.item(6).name
		outbound._remember(self.TARGET, a, a, "", "x")
		frappe.get_doc(
			{"doctype": "RD Item Scope", "item": a, "classification": "Restricted", "department": ""}
		).insert(ignore_permissions=True)
		assert not outbound.releasable(a)
		fake = FakeMirror()
		with mock.patch.object(outbound, "_client", return_value=fake):
			assert outbound.reconcile_target(self.TARGET) == 1
		assert fake.withdrawn == [a]
		assert not frappe.db.exists("RD External Record", {"target": self.TARGET, "item": a})

	def test_a_book_still_public_stays_and_a_deleted_one_goes(self):
		keep, drop = self.item(7).name, self.item(8).name
		for i in (keep, drop):
			outbound._remember(self.TARGET, i, i, "", "x")
		frappe.delete_doc("RD Item", drop, force=True, ignore_permissions=True)
		fake = FakeMirror()
		with mock.patch.object(outbound, "_client", return_value=fake):
			assert outbound.reconcile_target(self.TARGET) == 1
		assert fake.withdrawn == [drop]

	def test_a_withdrawal_is_made_even_in_a_dry_run(self):
		a = self.item(9, visibility="Login to read").name
		outbound._remember(self.TARGET, a, a, "", "x")
		frappe.db.set_value("RD Push Target", self.TARGET, "dry_run", 1)
		fake = FakeMirror()
		with mock.patch.object(outbound, "_client", return_value=fake):
			assert outbound.reconcile_target(self.TARGET) == 1
		assert fake.withdrawn == [a]

	def test_the_mirror_refuses_a_wrong_or_missing_token(self):
		for conf, sent in (
			({}, "x"),
			({"resdesk_mirror": 1}, "x"),
			({"resdesk_mirror": 1, "resdesk_mirror_token": "t" * 40}, "no"),
			({"resdesk_mirror": 1, "resdesk_mirror_token": "t" * 40}, "é"),
			({"resdesk_mirror": 1, "resdesk_mirror_token": "short"}, "short"),
		):
			with (
				mock.patch.object(frappe, "conf", frappe._dict(conf)),
				mock.patch.object(frappe, "get_request_header", return_value=sent),
			):
				with self.assertRaises(frappe.PermissionError):
					mirror._auth()

	def test_the_mirror_refuses_a_bad_identifier(self):
		for bad in ("", "../x", "a/b", ".hidden", "x" * 200):
			with self.assertRaises(frappe.ValidationError):
				mirror._folder(bad)
