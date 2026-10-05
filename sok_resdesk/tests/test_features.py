"""0.45: features switched on and off (not collected while off), institution profiles that
combine, and suggestions when data arrives that a switched-off feature would handle."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import features


class TestFeatures(IntegrationTestCase):
	def setUp(self):
		self.preset = frappe.db.get_single_value("RD Settings", "resource_preset")
		self.addCleanup(self._all_on)

	def _all_on(self):
		s = frappe.get_single("RD Settings")
		s.resource_preset = self.preset
		for key in features.PROFILES:
			s.set(f"profile_{key}", 0)
		for key in features.FEATURES:
			s.set(features.field_of(key), 1)
		s.save(ignore_permissions=True)
		frappe.db.delete("RD Item", {"name": ("like", "rdtestfeat%")})
		frappe.db.delete("RD Ingest Profile", {"name": ("like", "rdtest feat%")})
		frappe.cache.delete_value(features.SUGGESTIONS_KEY)
		frappe.db.commit()

	def switch(self, **values):
		s = frappe.get_single("RD Settings")
		for key, value in values.items():
			s.set(key, value)
		s.save(ignore_permissions=True)
		return s

	def test_profiles_combine(self):
		feats, preset = features.from_profiles(["small", "archive"])
		self.assertEqual(feats, {"ocr", "folders", "preservation", "identifiers", "review"})
		self.assertEqual(preset, "standard")  # the larger of light and standard
		s = self.switch(profile_small=1)
		self.assertEqual(s.resource_preset, "light")
		self.assertTrue(features.on("ocr"))
		self.assertFalse(features.on("notes"))
		s = self.switch(profile_archive=1)  # a second profile adds its features
		self.assertTrue(features.on("preservation") and features.on("ocr"))
		# a feature changed by hand stays as set while the profiles don't change
		s = self.switch(feature_notes=1)
		self.assertTrue(features.on("notes"))

	def test_switched_off_is_not_collected(self):
		self.switch(feature_notes=0, feature_review=0)
		from sok_resdesk import annotations, review

		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			annotations.add(item_id="nothing", leaf=1)
		with mock.patch("sok_resdesk.review.scan") as check:
			self.assertIsNone(review.nightly())
			check.assert_not_called()
		# the Desk: the review queue and the notes leave the workspace, and come back
		links = {(link.link_to) for link in frappe.get_doc("Workspace", "Research Desk").links}
		self.assertNotIn("resdesk-review", links)
		self.assertNotIn("RD Annotation", links)
		self.switch(feature_review=1)
		links = {(link.link_to) for link in frappe.get_doc("Workspace", "Research Desk").links}
		self.assertIn("resdesk-review", links)

	def test_sources_of_switched_off_features(self):
		self.switch(feature_folders=0)
		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": "rdtest feat folder",
					"source": "Folder or Server",
				}
			).insert(ignore_permissions=True)

	def test_data_suggests_a_switched_off_feature(self):
		self.switch(feature_reader_accounts=0)
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": "rdtestfeat1",
				"title": "Members only",
				"visibility": "Login to read",
			}
		).insert(ignore_permissions=True)
		frappe.cache.delete_value(features.SUGGESTIONS_KEY)
		hints = {h["feature"]: h for h in features.suggestions()}
		self.assertIn("reader_accounts", hints)
		self.assertGreaterEqual(hints["reader_accounts"]["count"], 1)
		features.switch_on("reader_accounts")
		self.assertTrue(features.on("reader_accounts"))
		self.assertNotIn("reader_accounts", {h["feature"] for h in features.suggestions()})

	def test_the_installers_answers(self):
		s = frappe.get_single("RD Settings")
		features.install_choices(s, "portal, archive,unknown", "60000")
		s.save(ignore_permissions=True)
		s.reload()
		self.assertEqual((s.profile_portal, s.profile_archive, s.profile_small), (1, 1, 0))
		self.assertTrue(features.on("preservation") and features.on("notes"))
		self.assertFalse(features.on("reader_accounts"))
		self.assertEqual(s.resource_preset, "server")  # a big catalogue, whatever the profiles say
		s = frappe.get_single("RD Settings")
		features.install_choices(s, "", None)  # no answer: nothing changes
		self.assertEqual(s.resource_preset, "server")
