"""0.48: books from Wikisource, through a whole ingest run. The wiki's API is stood in for
(sok_resdesk/tests/wikisource_fixtures.py); the catalogue, the run and its batches are real."""

from unittest import mock

import frappe

from sok_resdesk.core import wikisource as ws
from sok_resdesk.tests import wikisource_fixtures as fx
from sok_resdesk.tests.test_operations import OpsTestCase
from sok_resdesk.tests.wikisource_fixtures import Resp, Session

ITEM = "ws-kn-Kanaka.pdf"


class TestWikisourceSource(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit"})
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(self._clean)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest wikisource",
				"source": "Wikisource",
				"wiki_site": "kn.wikisource.org",
				"wiki_indexes": "Kanaka.pdf",
				"wiki_quality": "Proofread",
				"fetch_fulltext": 1,
				"max_items": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def _clean(self):
		for name in frappe.get_all("RD Item", filters={"name": ("like", "ws-kn-%")}, pluck="name"):
			frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)  # with its rows
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": ("in", ["Kanakadasa", "Other Poet"])})
		frappe.db.commit()

	def wiki(self):
		"""The wiki answering what a book needs, whichever way it is asked."""

		class Answers(Session):
			def get(this, url, params=None, timeout=None):
				this.asked.append(params)
				params = params or {}
				if params.get("meta") == "siteinfo":
					return Resp(fx.SITEINFO)
				if params.get("prop") == "imageinfo":
					return Resp(fx.FILEINFO)
				if params.get("generator") == "allpages":
					return Resp(fx.PAGES)
				return Resp(fx.INDEX_API)

		return ws.WikiClient("kn.wikisource.org", delay=0, session=Answers())

	def run_profile(self):
		from sok_resdesk.ingest import create_run, run_ingest

		with mock.patch("sok_resdesk.wikisource.client", side_effect=lambda profile: self.wiki()):
			run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
			frappe.db.commit()
			run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_a_book_with_its_proofread_pages(self):
		run = self.run_profile()
		self.assertEqual((run.status, run.created_count), ("Completed", 1), run.log)
		book = frappe.get_doc("RD Item", ITEM)
		self.assertEqual(book.source, "Wikisource")
		self.assertEqual((book.title, book.year, book.language), ("ಕನಕದಾಸ ಕೀರ್ತನೆಗಳು", 1931, "kan"))
		self.assertEqual((book.wiki_site, book.wiki_index), ("kn.wikisource.org", "Index:Kanaka.pdf"))
		self.assertEqual(book.source_url, "https://kn.wikisource.org/wiki/Index:Kanaka.pdf")
		self.assertEqual(book.page_count, 5)  # the scan's pages, not only those transcribed
		self.assertEqual(book.licence_url, ws.LICENCE)
		self.assertFalse(book.on_archive_org)
		# proofread and validated pages only: the unchecked and the blank page are left out
		self.assertEqual(book.text_source, "Wikisource (proofread)")
		from sok_resdesk.ingest import fetch_pages

		pages = fetch_pages(ITEM)
		self.assertEqual([p["leaf"] for p in pages], [0, 1])
		self.assertEqual(pages[1]["text"], "ಎರಡನೇ ಪುಟ")
		authors = sorted(r.creator for r in book.creators)
		self.assertEqual(authors, ["Kanakadasa", "Other Poet"])

	def test_the_pages_taken_follow_the_level(self):
		frappe.db.set_value("RD Ingest Profile", self.profile.name, "wiki_quality", "Any text")
		self.run_profile()
		book = frappe.get_doc("RD Item", ITEM)
		self.assertEqual(book.text_source, "Wikisource")  # not all proofread
		from sok_resdesk.ingest import fetch_pages

		self.assertEqual([p["leaf"] for p in fetch_pages(ITEM)], [0, 1, 2])
		frappe.db.set_value("RD Ingest Profile", self.profile.name, "wiki_quality", "Validated")
		self.run_profile()
		self.assertEqual([p["leaf"] for p in fetch_pages(ITEM)], [0])

	def test_page_images_come_from_the_wiki_and_the_book_is_a_iiif_manifest(self):
		self.run_profile()
		from sok_resdesk import api, iiif
		from sok_resdesk.catalogue import item_to_record

		record = item_to_record(frappe.get_doc("RD Item", ITEM))
		self.assertEqual(
			api.page_image_url(record, 1),
			"https://kn.wikisource.org/wiki/Special:Redirect/file/Kanaka.pdf?page=2&width=1000",
		)
		frappe.set_user("Guest")
		try:
			resp = iiif.manifest(ITEM)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(resp.status_code, 200)
		manifest = frappe.parse_json(resp.get_data(as_text=True))
		self.assertEqual(len(manifest["items"]), 5)
		body = manifest["items"][0]["items"][0]["items"][0]["body"]
		self.assertIn("Special:Redirect/file/Kanaka.pdf?page=1", body["id"])

	def test_an_unchanged_book_is_left_alone(self):
		self.run_profile()
		modified = frappe.db.get_value("RD Item", ITEM, "modified")
		second = self.run_profile()
		self.assertEqual(second.created_count, 0)
		self.assertEqual(frappe.db.get_value("RD Item", ITEM, "modified"), modified)

	def test_switched_off_with_the_repositories_feature(self):
		s = frappe.get_single("RD Settings")
		s.feature_repositories = 0
		s.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.set_single_value("RD Settings", "feature_repositories", 1))
		with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": "rdtest wikisource 2",
					"source": "Wikisource",
					"wiki_site": "kn.wikisource.org",
					"wiki_indexes": "X.pdf",
				}
			).insert(ignore_permissions=True)

	# -- 0.50: giving corrections back, as the person who made them --------------------------------

	def send_setup(self, licence="CC-BY-SA-4.0"):
		"""The book, a connected account, and the person's own work on three of its pages."""
		from sok_resdesk import pagetext

		self.run_profile()
		frappe.db.set_single_value("RD Settings", "ground_truth_licence", licence)
		self.addCleanup(lambda: frappe.db.set_single_value("RD Settings", "ground_truth_licence", ""))
		self.addCleanup(lambda: frappe.db.delete("RD Wikimedia Account", {"name": "Administrator"}))
		self.addCleanup(lambda: frappe.db.delete("RD Page Text", {"item": ITEM}))
		acc = frappe.get_doc(
			{
				"doctype": "RD Wikimedia Account",
				"user": "Administrator",
				"wikimedia_user": "Volunteer",
				"token": "t" * 40,
			}
		)
		acc.flags.ignore_permissions = True
		acc.insert()
		# page 3 (leaf 2): corrected here; page 2 (leaf 1): checked here, unchanged, validated by me
		pagetext.save(ITEM, 2, "corrected text", "Proofreading", "Proofread", reindex=False)
		pagetext.save(ITEM, 1, "ಎರಡನೇ ಪುಟ", "Proofreading", "Validated", reindex=False)
		frappe.db.set_value(
			"RD Page Text", {"item": ITEM, "leaf": 1, "is_current": 1}, "validated_by", "Administrator"
		)
		return pagetext

	def fake_wikimedia(self, page_user=None):
		"""Wikimedia as it answers edits and revision reads; `sent` collects the edits made."""
		pages = {
			p["title"]: p["revisions"][0]["slots"]["main"]["content"] for p in fx.PAGES["query"]["pages"]
		}
		for title, user in (page_user or {}).items():
			pages[title] = pages[title].replace('user="Reader"', f'user="{user}"')
		sent, revid = [], {"n": 100}

		def get(client, **params):
			out = []
			for title in params["titles"].split("|"):
				if title in pages:
					out.append(
						{
							"title": title,
							"revisions": [
								{
									"revid": revid["n"],
									"timestamp": "t",
									"slots": {"main": {"content": pages[title]}},
								}
							],
						}
					)
				else:
					out.append({"title": title, "missing": True})
			return {"query": {"pages": out}}

		def post(client, **data):
			if sent and data.get("fail"):
				raise AssertionError
			sent.append(data)
			return {"edit": {"result": "Success"}}

		for target, new in (
			("sok_resdesk.core.wikimedia.WikimediaClient.get", get),
			("sok_resdesk.core.wikimedia.WikimediaClient.post", post),
			("sok_resdesk.core.wikimedia.WikimediaClient.csrf", lambda client: "csrf+\\"),
			("sok_resdesk.wikisource.SEND_PAUSE", 0),
		):
			p = mock.patch(target, new)
			p.start()
			self.addCleanup(p.stop)
		return sent, revid

	def test_the_plan_is_only_my_own_work_checked_against_the_wiki(self):
		from sok_resdesk import wikisource

		self.send_setup()
		self.fake_wikimedia()
		plan = wikisource.send_plan(ITEM)
		self.assertEqual((plan["account"], plan["problem"]), ("Volunteer", ""))
		by_leaf = {p["leaf"]: p for p in plan["pages"]}
		self.assertEqual(sorted(by_leaf), [1, 2])  # nothing for pages I did nothing to
		self.assertEqual((by_leaf[2]["kind"], by_leaf[2]["to_level"]), ("proofread", 3))
		self.assertIn("+corrected text", by_leaf[2]["diff"])
		# proofread there by Reader, unchanged and validated here by me: a second pair of eyes
		self.assertEqual((by_leaf[1]["kind"], by_leaf[1]["to_level"]), ("validated", 4))

	def test_my_proofreading_of_a_page_is_not_my_validation_of_it(self):
		from sok_resdesk import wikisource

		self.send_setup()
		self.fake_wikimedia()
		# someone else corrected page 3 here: it is theirs to send
		frappe.db.set_value(
			"RD Page Text", {"item": ITEM, "leaf": 2, "is_current": 1}, "proofread_by", "Guest"
		)
		by_leaf = {p["leaf"]: p for p in wikisource.send_plan(ITEM)["pages"]}
		self.assertEqual(by_leaf[2]["kind"], "")
		self.assertIn("someone else", by_leaf[2]["skip"])
		# the wiki says I proofread page 2 myself: Wikisource wants a different validator
		self.fake_wikimedia(page_user={"Page:Kanaka.pdf/2": "Volunteer"})
		by_leaf = {p["leaf"]: p for p in wikisource.send_plan(ITEM)["pages"]}
		self.assertIn("another person", by_leaf[1]["skip"])

	def test_pages_with_markup_or_already_proofread_there_are_never_overwritten(self):
		from sok_resdesk import pagetext, wikisource

		self.send_setup()
		self.fake_wikimedia()
		# page 1 (leaf 0) is validated on the wiki; page 2 (leaf 1) is proofread there and changed here
		pagetext.save(ITEM, 0, "mine", "Proofreading", "Proofread", reindex=False)
		pagetext.save(ITEM, 1, "different", "Proofreading", "Proofread", reindex=False)
		by_leaf = {p["leaf"]: p for p in wikisource.send_plan(ITEM)["pages"]}
		self.assertIn("Already validated", by_leaf[0]["skip"])
		self.assertIn("not overwritten", by_leaf[1]["skip"])

	def test_sending_edits_the_page_as_me_and_names_the_revision(self):
		from sok_resdesk import wikisource

		self.send_setup()
		sent, _revid = self.fake_wikimedia()
		out = wikisource.send_pages(ITEM, [{"leaf": 2, "revid": 100}, {"leaf": 1, "revid": 100}])
		self.assertEqual([r["result"] for r in out], ["proofread", "validated"])
		first, second = sent
		self.assertEqual(
			(first["title"], first["baserevid"], first["nocreate"]), ("Page:Kanaka.pdf/3", 100, 1)
		)
		self.assertIn('<pagequality level="3" user="Volunteer" /></noinclude>corrected text', first["text"])
		self.assertIn('<pagequality level="4" user="Volunteer" /></noinclude>ಎರಡನೇ ಪುಟ', second["text"])
		self.assertNotIn("bot", first)  # a person's edit, not a bot's
		self.assertIsNotNone(frappe.db.get_value("RD Wikimedia Account", "Administrator", "last_used"))

	def test_a_page_that_changed_since_the_review_is_not_sent(self):
		from sok_resdesk import wikisource
		from sok_resdesk.core.wikimedia import WikimediaError

		self.send_setup()
		sent, _revid = self.fake_wikimedia()
		out = wikisource.send_pages(ITEM, [{"leaf": 2, "revid": 99}])  # reviewed against an older revision
		self.assertIn("changed on Wikisource", out[0]["result"])
		self.assertEqual(sent, [])
		# the wiki's own check, if someone edits between our read and our edit
		with mock.patch(
			"sok_resdesk.core.wikimedia.WikimediaClient.post", side_effect=WikimediaError("editconflict: x")
		):
			out = wikisource.send_pages(ITEM, [{"leaf": 2, "revid": 100}])
		self.assertIn("changed on Wikisource meanwhile", out[0]["result"])

	def test_without_a_licence_or_an_account_nothing_is_sent(self):
		from sok_resdesk import wikisource

		self.send_setup(licence="")
		self.fake_wikimedia()
		self.assertIn("Choose the licence", wikisource.send_plan(ITEM)["problem"])
		with self.assertRaisesRegex(frappe.ValidationError, "Choose the licence"):
			wikisource.send_pages(ITEM, [{"leaf": 2, "revid": 100}])
		frappe.db.set_single_value("RD Settings", "ground_truth_licence", "CC-BY-SA-4.0")
		frappe.db.delete("RD Wikimedia Account", {"name": "Administrator"})
		self.assertIn("Connect your own", wikisource.send_plan(ITEM)["problem"])
