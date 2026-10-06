"""0.66: giving a book to the Internet Archive under the sender's own account.
archive.org is stood in for; the item, its files, the accounts and the checks are real."""

import os
import tempfile
from unittest import mock

import frappe

from sok_resdesk import archive_upload
from sok_resdesk.tests.test_operations import OpsTestCase, _item

LICENCE = "https://creativecommons.org/licenses/by/4.0/"
DEPOSITOR = "rdtest-ia-dep@example.org"
STAFFER = "rdtest-ia-staff@example.org"


class FakeIA:
	"""An archive.org that records what it is given."""

	taken = False
	uploads: list = []

	def __init__(self, access, secret, session=None):
		self.keys = (access, secret)

	def check(self):
		return "volunteer"

	def exists(self, identifier):
		return FakeIA.taken

	def upload(self, identifier, name, fileobj, headers=None):
		FakeIA.uploads.append((identifier, name, fileobj.read(), headers))


def _user(email, role):
	if not frappe.db.exists("Role", role):
		frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)


class TestArchiveUpload(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value(
			"RD Settings", {"feature_sharing": 1, "ia_upload_collection": "opensource"}
		)
		FakeIA.taken, FakeIA.uploads = False, []
		_user(DEPOSITOR, "ResDesk Depositor")
		_user(STAFFER, "ResDesk Cataloguer")
		self.item = _item(95)
		frappe.db.set_value(
			"RD Item",
			self.item,
			{
				"published": 1,
				"visibility": "Public",
				"access_status": "Open",
				"licence_url": LICENCE,
				"source": "Local",
				"on_archive_org": 0,
				"title": "Rdtest Given Book",
				"year": 1950,
			},
		)
		self.file = os.path.join(tempfile.mkdtemp(), "book.pdf")
		with open(self.file, "wb") as f:
			f.write(b"%PDF-1.4 test")
		for patcher in (
			mock.patch.object(archive_upload, "IAWriter", FakeIA),
			mock.patch.object(archive_upload, "_files", lambda doc: [("book.pdf", self.file)]),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		for user in ("Administrator", DEPOSITOR, STAFFER):
			frappe.db.delete(archive_upload.DOCTYPE, {"name": user})
		frappe.db.commit()
		self.addCleanup(self.forget)

	def forget(self):
		frappe.set_user("Administrator")
		for user in ("Administrator", DEPOSITOR, STAFFER):
			frappe.db.delete(archive_upload.DOCTYPE, {"name": user})
		frappe.db.delete("RD Deposit", {"title": "Rdtest Given Book"})
		frappe.db.commit()

	def job(self, kw):
		return {k: v for k, v in kw.items() if k not in ("queue", "timeout")}

	def connect(self, user="Administrator"):
		frappe.set_user(user)
		return archive_upload.connect("ACCESS", "SECRET")

	def test_keys_are_checked_kept_and_never_shown(self):
		out = self.connect()
		self.assertEqual((out["connected"], out["ia_user"]), (True, "volunteer"))
		self.assertNotIn("SECRET", str(out))
		self.assertEqual(archive_upload._my_keys("Administrator"), ("ACCESS", "SECRET"))
		archive_upload.disconnect()
		self.assertFalse(archive_upload.status()["connected"])

	def test_the_plan_names_what_goes_and_what_stops_it(self):
		frappe.set_user("Administrator")
		self.assertIn("Connect your archive.org", archive_upload.plan(self.item)["problem"])
		self.connect()
		p = archive_upload.plan(self.item)
		self.assertEqual(p["problem"], "")
		self.assertTrue(p["identifier"].startswith("Rdtest-Given-Book"))
		self.assertEqual(
			(p["collection"], p["files"][0]["name"], p["public"]), ("opensource", "book.pdf", True)
		)
		frappe.db.set_value("RD Item", self.item, "visibility", "Login to read")
		self.assertIn("public", archive_upload.plan(self.item)["problem"])
		frappe.db.set_value("RD Item", self.item, {"visibility": "Public", "licence_url": ""})
		self.assertIn("licence", archive_upload.plan(self.item)["problem"])

	def test_a_taken_identifier_is_refused(self):
		self.connect()
		FakeIA.taken = True
		p = archive_upload.plan(self.item)
		self.assertTrue(p["name_taken"])
		with self.assertRaises(frappe.ValidationError):
			archive_upload.send(self.item, p["identifier"], confirmed=1)

	def test_sending_needs_confirmation_then_queues_and_uploads_publicly(self):
		self.connect()
		ident = archive_upload.plan(self.item)["identifier"]
		with self.assertRaises(frappe.ValidationError):
			archive_upload.send(self.item, ident)
		out = archive_upload.send(self.item, ident, confirmed=1)
		self.assertEqual(out["status"], "Queued")
		self.assertEqual(frappe.db.get_value("RD Item", self.item, "ia_sent_status"), "Queued")
		(method, kw) = self.enqueued[-1]
		self.assertEqual(method, "sok_resdesk.archive_upload.run_upload")
		archive_upload.run_upload(**self.job(kw))
		self.assertEqual(frappe.db.get_value("RD Item", self.item, "ia_sent_status"), "On archive.org")
		identifier, name, body, headers = FakeIA.uploads[0]
		self.assertEqual((identifier, name, body), (ident, "book.pdf", b"%PDF-1.4 test"))
		self.assertEqual(headers["x-archive-meta-collection"], "opensource")
		self.assertEqual(headers["x-archive-meta-licenseurl"], LICENCE)
		# it cannot be sent twice
		self.assertIn("Already sent", archive_upload.plan(self.item)["problem"])

	def test_a_failed_upload_is_recorded_and_can_be_sent_again(self):
		self.connect()
		ident = archive_upload.plan(self.item)["identifier"]
		archive_upload.send(self.item, ident, confirmed=1)
		kw = self.enqueued[-1][1]
		with mock.patch.object(FakeIA, "upload", side_effect=RuntimeError("boom")):
			archive_upload.run_upload(**self.job(kw))
		self.assertEqual(frappe.db.get_value("RD Item", self.item, "ia_sent_status"), "Failed")
		FakeIA.taken = True  # the half-made item exists: sending the same identifier again resumes
		self.assertEqual(archive_upload.plan(self.item, ident)["problem"], "")
		self.assertFalse(archive_upload.plan(self.item, ident)["name_taken"])

	def test_a_depositor_sends_only_their_own_work_into_the_librarys_collection(self):
		self.connect(DEPOSITOR)
		with self.assertRaises(frappe.PermissionError):
			archive_upload.plan(self.item)
		frappe.set_user("Administrator")
		dep = frappe.get_doc(
			{
				"doctype": "RD Deposit",
				"title": "Rdtest Given Book",
				"depositor": DEPOSITOR,
				"item": self.item,
				"status": "Accepted",
			}
		)
		dep.flags.ignore_permissions = dep.flags.ignore_mandatory = dep.flags.ignore_validate = True
		dep.db_insert()
		frappe.set_user(DEPOSITOR)
		p = archive_upload.plan(self.item, collection="another")
		self.assertEqual(
			(p["collection"], p["may_choose_collection"], p["problem"]), ("opensource", False, "")
		)

	def test_staff_choose_the_collection(self):
		self.connect()
		p = archive_upload.plan(self.item, collection="community-books")
		self.assertEqual((p["collection"], p["may_choose_collection"]), ("community-books", True))
