"""0.53: repository deposit, from a person's draft to a book on the portal. The search engine and
mail are stood in for; the roles, the files on disk, the review rules and the catalogue are real."""

import os
import shutil
from unittest import mock

import frappe

from sok_resdesk import deposit
from sok_resdesk.tests.oai_fixtures import make_pdf
from sok_resdesk.tests.test_operations import OpsTestCase

DEPOSITOR, OTHER, REVIEWER = (f"rdtest-{n}@example.com" for n in ("depositor", "other", "reviewer"))
PAGES = ["A deposited paper, first page", "Its second page with words"]


def _user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)


class TestDeposit(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit", "feature_deposit": 1})
		for role in ("ResDesk Depositor", "ResDesk Cataloguer"):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
		_user(DEPOSITOR, "ResDesk Depositor")
		_user(OTHER, "ResDesk Depositor")
		_user(REVIEWER, "ResDesk Cataloguer")
		self.mail = []
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
			mock.patch("sok_resdesk.deposit._tell", side_effect=lambda *a: self.mail.append(a)),
		):
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(self._clean)
		frappe.db.commit()

	def _clean(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("RD Item", filters={"name": ("like", "dep-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("RD Deposit", pluck="name"):
			frappe.delete_doc("RD Deposit", name, force=True, ignore_permissions=True)
		frappe.db.delete("File", {"attached_to_doctype": "RD Deposit"})
		frappe.db.delete("RD Collection", {"name": "rdtest-dep-collection"})
		shutil.rmtree(frappe.get_site_path("private", "deposits"), ignore_errors=True)
		frappe.db.set_single_value("RD Settings", "feature_deposit", 1)
		frappe.db.commit()

	def make(self, user=DEPOSITOR, **extra):
		frappe.set_user(user)
		values = {
			"title": "rdtest deposited paper",
			"creators": "Rao, Kamala\nSmith, John",
			"abstract": "About something.",
			"subjects": "palm leaf\nrdtest",
			"year": 2024,
			"language": "eng",
			"item_type": "Article",
			"licence": "CC-BY-4.0",
			"access": "Public",
			"declaration": 1,
			**extra,
		}
		return deposit.save(values)

	def add_file(self, name, file_name="paper.pdf", content=None):
		content = content or make_pdf(PAGES)
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": file_name,
				"content": content,
				"is_private": 1,
				"attached_to_doctype": "RD Deposit",
				"attached_to_name": name,
			}
		).insert(ignore_permissions=True)
		return deposit.attach_file(name, f.file_url)

	def test_from_a_draft_to_a_book_on_the_portal(self):
		from sok_resdesk.ingest import fetch_pages

		frappe.get_doc(
			{
				"doctype": "RD Collection",
				"title": "rdtest-dep-collection",
				"slug": "rdtest-dep-collection",
				"published": 1,
			}
		).insert(ignore_permissions=True) if not frappe.db.exists(
			"RD Collection", "rdtest-dep-collection"
		) else None
		name = self.make(
			collection="rdtest-dep-collection"
			if frappe.db.exists("RD Collection", "rdtest-dep-collection")
			else None
		)
		with self.assertRaisesRegex(frappe.ValidationError, "at least one file"):
			deposit.submit(name)
		row = self.add_file(name)
		self.assertEqual((row["file_name"], row["format"]), ("paper.pdf", "PDF"))
		frappe.db.set_value("RD Deposit", name, "declaration", 0)
		with self.assertRaisesRegex(frappe.ValidationError, "declaration"):
			deposit.submit(name)
		frappe.db.set_value("RD Deposit", name, "declaration", 1)
		self.assertEqual(deposit.submit(name)["status"], "Submitted")
		self.assertTrue(any("New deposit to review" in m[1] for m in self.mail))
		# a depositor cannot change it any more, nor accept anything
		with self.assertRaises(frappe.ValidationError):
			deposit.save({"title": "changed"}, name)
		with self.assertRaises(frappe.PermissionError):
			deposit.accept(name)
		# someone else on the staff reviews and accepts
		frappe.set_user(REVIEWER)
		result = deposit.accept(name, "Thank you")
		item = result["item"]
		self.assertEqual(item, "dep-" + name.split("-")[1].lower())
		book = frappe.get_doc("RD Item", item)
		self.assertEqual(
			(book.title, book.published, book.visibility, book.item_type),
			("rdtest deposited paper", 1, "Public", "Article"),
		)
		self.assertEqual((book.source, book.year, book.language), ("Local", 2024, "eng"))
		self.assertEqual(sorted(r.creator for r in book.creators), ["Rao, Kamala", "Smith, John"])
		self.assertEqual(book.licence_url, "https://creativecommons.org/licenses/by/4.0/")
		self.assertIn("Deposited by", book.rights)
		self.assertEqual(book.local_pdf, "paper.pdf")
		self.assertTrue(book.lock_metadata)
		self.assertEqual((book.text_source, book.page_count), ("PDF text layer", 2))
		self.assertEqual(fetch_pages(item)[1]["text"], PAGES[1])
		dep = frappe.get_doc("RD Deposit", name)
		self.assertEqual((dep.status, dep.item, dep.reviewer), ("Accepted", item, REVIEWER))
		self.assertTrue(any("accepted" in m[1] for m in self.mail))
		# the file in the book's folder is the one deposited
		path = os.path.join(frappe.get_site_path("private", "deposits"), item, "paper.pdf")
		self.assertEqual(deposit.core.sha256_of(path), dep.files[0].sha256)
		# and a reader can download it
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api

		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.set_user("Guest")
		response = api.file(item, "paper.pdf")
		response.direct_passthrough = False
		self.assertEqual(response.get_data(), make_pdf(PAGES))

	def test_staff_cannot_review_their_own_deposit_and_changes_can_be_asked_for(self):
		name = self.make(user=REVIEWER)
		self.add_file(name)
		deposit.submit(name)
		with self.assertRaisesRegex(frappe.ValidationError, "Someone else"):
			deposit.accept(name)
		frappe.set_user(
			"Administrator"
		)  # a System Manager can (the only person there is, in a small library)
		deposit.request_changes(name, "Please add the abstract")
		self.assertEqual(frappe.db.get_value("RD Deposit", name, "status"), "Needs Changes")
		# the depositor may change it again, and submit it again
		frappe.set_user(REVIEWER)
		deposit.save({"abstract": "Now with an abstract"}, name)
		self.assertEqual(deposit.submit(name)["status"], "Submitted")
		frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "Say why"):
			deposit.reject(name, " ")
		self.assertEqual(deposit.reject(name, "Out of scope")["status"], "Rejected")
		self.assertFalse(frappe.db.exists("RD Item", "dep-" + name.split("-")[1].lower()))

	def test_an_embargo_keeps_the_files_for_logged_in_readers_until_its_date(self):
		name = self.make(embargo_until=frappe.utils.add_days(frappe.utils.nowdate(), 30))
		self.add_file(name)
		deposit.submit(name)
		frappe.set_user(REVIEWER)
		item = deposit.accept(name)["item"]
		self.assertEqual(frappe.db.get_value("RD Item", item, "visibility"), "Login to read")
		frappe.set_user("Administrator")
		self.assertEqual(deposit.release_embargoes(), 0)  # not yet
		frappe.db.set_value(
			"RD Deposit", name, "embargo_until", frappe.utils.add_days(frappe.utils.nowdate(), -1)
		)
		self.assertEqual(deposit.release_embargoes(), 1)
		self.assertEqual(frappe.db.get_value("RD Item", item, "visibility"), "Public")
		self.assertEqual(deposit.release_embargoes(), 0)  # once

	def test_only_documents_within_the_size_limit_come_in_and_repeats_are_flagged(self):
		name = self.make()
		with self.assertRaisesRegex(frappe.ValidationError, "only pdf"):
			self.add_file(name, "program.exe", b"MZ....")
		with mock.patch("sok_resdesk.deposit.max_mb", return_value=0):
			with self.assertRaisesRegex(frappe.ValidationError, "limit"):
				self.add_file(name, "big.pdf", make_pdf(["x"]))
		self.add_file(name)
		deposit.submit(name)
		again = self.make(title="rdtest the same file again")
		self.add_file(again)
		deposit.submit(again)
		self.assertIn(name, frappe.db.get_value("RD Deposit", again, "warnings"))

	def test_nobody_reads_or_changes_another_persons_deposit(self):
		name = self.make()
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			deposit.get(name)
		with self.assertRaises(frappe.PermissionError):
			deposit.save({"title": "mine now"}, name)
		self.assertEqual(deposit.mine(), [])
		frappe.set_user(DEPOSITOR)
		self.assertEqual([r.name for r in deposit.mine()], [name])
		self.assertEqual(deposit.withdraw(name)["status"], "Withdrawn")

	def test_a_reader_without_the_role_cannot_deposit_and_the_feature_can_be_off(self):
		_user("rdtest-reader@example.com", "ResDesk Reader")
		self.addCleanup(lambda: frappe.delete_doc("User", "rdtest-reader@example.com", force=True))
		frappe.set_user("rdtest-reader@example.com")
		with self.assertRaises(frappe.PermissionError):
			deposit.save({"title": "x"})
		frappe.set_user("Administrator")
		frappe.db.set_single_value("RD Settings", "feature_deposit", 0)
		frappe.set_user(DEPOSITOR)
		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			deposit.save({"title": "x"})
