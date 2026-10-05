"""0.44.1: help pictures are never stuck on an old version: shipped ones carry the version in
their address, and a library's own stand in only while the screen they show is unchanged."""

import hashlib
import json
import shutil
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import __version__, help


class TestHelpPictures(IntegrationTestCase):
	def setUp(self):
		self.folder = Path(frappe.get_site_path("public", "files", help.SITE_PICTURES))
		self.had = self.folder.exists()
		if self.had:
			self.backup = self.folder.with_name("resdesk-guide-test-backup")
			shutil.rmtree(self.backup, ignore_errors=True)
			shutil.move(self.folder, self.backup)
		self.folder.mkdir(parents=True)
		self.addCleanup(self._restore)

	def _restore(self):
		shutil.rmtree(self.folder, ignore_errors=True)
		if self.had:
			shutil.move(self.backup, self.folder)

	def take(self, taken):
		for name in taken:
			(self.folder / name).write_bytes(b"our own picture")
		(self.folder / help.TAKEN).write_text(json.dumps(taken))

	def test_shipped_pictures_carry_the_version(self):
		self.assertEqual(
			help.image_url("desk-workspace.png"),
			f"/assets/sok_resdesk/images/guide/desk-workspace.png?v={__version__}",
		)

	def test_own_pictures_only_while_the_screen_is_unchanged(self):
		shipped = hashlib.sha256(help._shipped("desk-workspace.png").read_bytes()).hexdigest()
		self.take({"desk-workspace.png": shipped, "desk-items.png": "an older picture", "ours-only.png": ""})
		self.assertTrue(
			help.image_url("desk-workspace.png").startswith("/files/resdesk-guide/desk-workspace.png?v=")
		)
		# an upgrade changed the Items screen since this library took its picture: the new shipped one
		self.assertIn("/assets/", help.image_url("desk-items.png"))
		self.assertTrue(help.image_url("ours-only.png").startswith("/files/"))
		self.assertEqual(help.outdated_site_pictures(), 1)

	def test_pictures_taken_before_this_was_recorded_count_as_old(self):
		(self.folder / "desk-workspace.png").write_bytes(b"our own picture")
		self.assertIn("/assets/", help.image_url("desk-workspace.png"))
		self.assertEqual(help.outdated_site_pictures(), 1)
