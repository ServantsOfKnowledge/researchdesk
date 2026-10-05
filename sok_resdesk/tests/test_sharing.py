"""Integration tests for 0.30, sharing the loop: ground-truth sets, notes as data (Wikidata items,
tags), the W3C Web Annotation Protocol, DOIs from DataCite, and the catalogue-first ingest.
They need a site but no network (archive.org, Wikidata and DataCite are stood in for)."""

import io
import json
import os
from unittest import mock

import frappe

from sok_resdesk.tests.test_operations import PREFIX, OpsTestCase, _item

MORE_SETTINGS = (
	"ground_truth_licence",
	"ground_truth_attribution",
	"ground_truth_names",
	"doi_enabled",
	"datacite_test",
	"doi_prefix",
	"doi_shoulder",
	"datacite_repository",
	"book_limit",
)


def _jpeg() -> bytes:
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (300, 400), "white").save(buf, format="JPEG")
	return buf.getvalue()


class SharingTestCase(OpsTestCase):
	def setUp(self):
		super().setUp()
		self._more = {f: frappe.db.get_single_value("RD Settings", f) for f in MORE_SETTINGS}
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("RD Settings", self._more)
		frappe.db.commit()


class TestGroundTruth(SharingTestCase):
	def setUp(self):
		super().setUp()
		from sok_resdesk import pagetext
		from sok_resdesk.core import zones as zn

		frappe.db.set_single_value("RD Settings", {"ground_truth_licence": "", "ground_truth_names": 0})
		self.book = _item(91)
		frappe.db.set_value("RD Item", self.book, {"visibility": "Public", "language": "kan"})
		two = [zn.zone(2, 2, 48, 96), zn.zone(50, 2, 48, 96)]
		pagetext.save(self.book, 3, "ಎಡ ಕಾಲಮ್\n\nಬಲ ಕಾಲಮ್", "Proofreading", "Proofread", two, reindex=False)
		frappe.db.commit()
		self.addCleanup(self.cleanup)

	def cleanup(self):
		from sok_resdesk.groundtruth import remove_file

		for name in frappe.get_all("RD Ground Truth", filters={"title": ("like", "rdtest%")}, pluck="name"):
			remove_file(frappe.get_doc("RD Ground Truth", name))
			frappe.delete_doc("RD Ground Truth", name, force=True)
		frappe.db.delete("RD Page Text", {"item": self.book})
		frappe.db.commit()

	def make(self, **kw):
		doc = frappe.get_doc({"doctype": "RD Ground Truth", "title": "rdtest set", "item": self.book, **kw})
		return doc.insert()

	def build(self, name):
		from sok_resdesk import groundtruth

		with mock.patch("sok_resdesk.reocr.page_image", return_value=_jpeg()):
			groundtruth.build_job(name)
		return frappe.get_doc("RD Ground Truth", name)

	def test_a_set_is_made_and_kept_private_until_a_licence_is_chosen(self):
		from sok_resdesk import groundtruth

		doc = self.make()
		self.assertEqual(groundtruth.preview(doc.name)["pages"], 1)
		doc = self.build(doc.name)
		self.assertEqual((doc.status, doc.page_count, doc.zone_count, doc.book_count), ("Ready", 1, 2, 1))
		self.assertFalse(doc.licence)
		path = os.path.join(groundtruth.folder(), doc.file_name)
		self.assertTrue(os.path.isfile(path))
		with self.assertRaises(frappe.ValidationError):
			groundtruth.publish(doc.name, 1)
		self.assertEqual(groundtruth.public_sets(), [])

		frappe.db.set_single_value("RD Settings", "ground_truth_licence", "CC0-1.0")
		doc = self.build(doc.name)
		self.assertEqual(doc.licence, "CC0-1.0")
		groundtruth.publish(doc.name, 1)
		self.assertIn(doc.name, [s.name for s in groundtruth.public_sets()])
		frappe.delete_doc("RD Ground Truth", doc.name, force=True)
		self.assertFalse(os.path.isfile(path))  # the file goes with the set

	def test_which_pages(self):
		from sok_resdesk import groundtruth

		self.assertEqual(groundtruth.preview(self.make(pages_wanted="Validated only").name)["pages"], 0)
		frappe.db.set_value("RD Item", self.book, "visibility", "Login to read")
		self.assertEqual(groundtruth.preview(self.make().name)["pages"], 0)  # members' books stay out
		self.assertEqual(groundtruth.preview(self.make(public_books_only=0).name)["pages"], 1)


class TestNotesAsData(SharingTestCase):
	TEXT = "Purandara Dasa sang at Hampi; Hampi was the capital."

	def setUp(self):
		super().setUp()
		from sok_resdesk.ingest import write_cached_pages

		self.reader = "rdtest-reader-w@example.com"
		if not frappe.db.exists("User", self.reader):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": self.reader,
					"first_name": "W",
					"send_welcome_email": 0,
					"user_type": "Website User",
				}
			).insert(ignore_permissions=True)
		self.book = _item(92)
		frappe.db.set_value("RD Item", self.book, {"has_page_text": 1, "visibility": "Public"})
		write_cached_pages(self.book, [{"leaf": 4, "label": "2", "text": self.TEXT}])
		frappe.local.request_ip = "127.0.0.1"
		patcher = mock.patch(
			"sok_resdesk.annotations.describe",
			side_effect=lambda ids, language="en": {
				q: {"label": "Purandara Dasa", "description": "composer"} for q in ids
			},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.db.commit()
		self.addCleanup(lambda: (frappe.db.delete("RD Annotation", {"item": self.book}), frappe.db.commit()))

	def add(self, **kw):
		from sok_resdesk import annotations

		frappe.set_user(self.reader)
		start = self.TEXT.index("Purandara")
		return annotations.add(self.book, 4, start=start, end=start + 14, **kw)

	def test_a_note_without_a_mouse(self):
		from sok_resdesk import annotations

		frappe.set_user(self.reader)
		typed = annotations.add(self.book, 4, kind="Comment", body="where", quote="Hampi was the capital")
		self.assertEqual(
			(typed["exact"], typed["pos_start"]), ("Hampi was the capital", self.TEXT.index("Hampi was"))
		)
		page = annotations.add(self.book, 4, kind="Comment", body="the whole page")
		self.assertFalse(page["exact"] or page["region"])  # on the whole page
		with self.assertRaises(frappe.ValidationError):
			annotations.add(self.book, 4, kind="Comment", body="x", quote="not on this page")

	def test_a_note_names_what_it_is_about(self):
		from sok_resdesk import annotations

		note = self.add(kind="Comment", body="the composer", entity="https://www.wikidata.org/wiki/Q2724213")
		self.assertEqual((note["entity"], note["entity_label"]), ("Q2724213", "Purandara Dasa"))
		with self.assertRaises(frappe.ValidationError):
			self.add(kind="Comment", body="x", entity="Hampi")
		link = self.add(kind="Link", link="https://www.wikidata.org/wiki/Q1010")
		self.assertEqual(link["entity"], "Q1010")  # a link to Wikidata says what it is about

		public = self.add(kind="Tag", tags="haridasa, music", entity="Q2724213", visibility="Public")
		frappe.set_user("Administrator")
		self.assertEqual(annotations.notes_about("Q2724213"), [])  # not approved yet
		annotations.review(public["name"], "Approved")
		self.assertTrue(any(m == "sok_resdesk.search.update_item_fields" for m, _ in self.enqueued))
		frappe.set_user(self.reader)
		about = annotations.notes_about("Q2724213")
		self.assertEqual([n["name"] for n in about], [public["name"]])
		self.assertEqual([n["name"] for n in annotations.notes_tagged("Music")], [public["name"]])
		labels = annotations.public_labels(self.book)
		self.assertEqual(labels["note_entities"], ["Q2724213"])
		self.assertEqual(labels["note_tags"], ["haridasa", "music"])
		self.assertEqual(annotations.by_book(about)[0]["item"], self.book)


class TestAnnotationProtocol(TestNotesAsData):
	def call(self, method, path="", body=None, headers=None):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import annotation_protocol as ap

		env = EnvironBuilder(
			path=f"/api/method/{ap.ENDPOINT}/{self.book}/{path}",
			method=method,
			data=json.dumps(body) if body is not None else None,
			content_type="application/ld+json",
			headers=headers or {},
		).get_environ()
		saved = getattr(frappe.local, "request", None)
		frappe.local.request = Request(env)
		try:
			return ap.annotations()
		finally:
			frappe.local.request = saved

	def anno(self, comment="the composer"):
		return {
			"@context": "http://www.w3.org/ns/anno.jsonld",
			"type": "Annotation",
			"motivation": "commenting",
			"body": [
				{"type": "TextualBody", "value": comment, "purpose": "commenting"},
				{
					"type": "SpecificResource",
					"source": "http://www.wikidata.org/entity/Q2724213",
					"purpose": "identifying",
				},
			],
			"target": {
				"source": f"https://lib.example/library/item/{self.book}?page=4",
				"selector": {"type": "TextQuoteSelector", "exact": "Purandara Dasa", "suffix": " sang"},
			},
		}

	def test_another_tool_reads_and_writes_notes(self):
		frappe.set_user("Guest")
		self.assertEqual(self.call("POST", body=self.anno()).status_code, 401)
		frappe.set_user(self.reader)
		made = self.call("POST", body=self.anno())
		self.assertEqual(made.status_code, 201, made.get_data(as_text=True))
		anno = json.loads(made.get_data())
		self.assertEqual(made.headers["Location"], anno["id"])
		name = anno["id"].rsplit("/", 1)[-1]
		self.assertEqual(
			frappe.db.get_value("RD Annotation", name, ["visibility", "entity", "pos_start"]),
			("Private", "Q2724213", 0),
		)

		got = self.call("GET", name)
		self.assertEqual(got.status_code, 200)
		etag = got.headers["ETag"]
		self.assertEqual(
			self.call("PUT", name, self.anno("changed"), {"If-Match": '"stale"'}).status_code, 412
		)
		put = self.call("PUT", name, self.anno("changed"), {"If-Match": etag})
		self.assertEqual(put.status_code, 200, put.get_data(as_text=True))
		self.assertEqual(frappe.db.get_value("RD Annotation", name, "body"), "changed")

		container = json.loads(self.call("GET").get_data())
		self.assertEqual(container["total"], 1)
		page = json.loads(self.call("GET", "?page=0").get_data())  # path then query
		self.assertEqual(page["type"], "AnnotationPage")
		frappe.set_user("Guest")
		self.assertEqual(json.loads(self.call("GET").get_data())["total"], 0)  # it is private
		self.assertEqual(self.call("GET", name).status_code, 404)
		frappe.set_user(self.reader)
		self.assertEqual(self.call("DELETE", name).status_code, 204)
		self.assertFalse(frappe.db.exists("RD Annotation", name))
		bad = self.anno()
		bad["target"]["selector"]["exact"] = "not on the page"
		self.assertEqual(self.call("POST", body=bad).status_code, 400)


class FakeDataCite:
	def __init__(self):
		self.calls = []

	def put(self, url, json=None, timeout=None):
		self.calls.append(("PUT", url, json))
		return mock.Mock(status_code=404 if len(self.calls) == 1 else 200)

	def post(self, url, json=None, timeout=None):
		self.calls.append(("POST", url, json))
		return mock.Mock(status_code=201)


class TestDOIs(SharingTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value(
			"RD Settings",
			{
				"doi_enabled": 1,
				"datacite_test": 1,
				"doi_prefix": "10.12345",
				"doi_shoulder": "rd.",
				"datacite_repository": "SOK.TEST",
			},
		)
		self.book = _item(93)
		frappe.db.set_value("RD Item", self.book, "visibility", "Public")
		coll = frappe.get_doc(
			{"doctype": "RD Collection", "title": "rdtest dois", "give_dois": 1, "published": 1}
		).insert()
		self.coll = coll.name
		frappe.get_doc(
			{
				"doctype": "RD Item Collection",
				"parent": self.book,
				"parenttype": "RD Item",
				"parentfield": "curated_collections",
				"collection": self.coll,
			}
		).db_insert()
		frappe.db.commit()

	def test_books_of_a_collection_get_dois(self):
		from sok_resdesk import datacite
		from sok_resdesk.catalogue import get_record

		self.assertIn(self.book, datacite.wanted())
		fake = FakeDataCite()
		session = (fake, "https://api.test.datacite.org", datacite._settings())
		self.assertEqual(datacite.register(self.book, session), "made")
		doi = f"10.12345/RD.{self.book.upper()}"
		self.assertEqual(frappe.db.get_value("RD Item", self.book, ["doi", "doi_state"]), (doi, "Test"))
		self.assertEqual([c[0] for c in fake.calls], ["PUT", "POST"])  # not there yet: created
		self.assertEqual(fake.calls[1][2]["data"]["attributes"]["event"], "publish")
		self.assertEqual(datacite.register(self.book, session), "unchanged")
		self.assertFalse(get_record(self.book).get("doi"))  # a test DOI is never cited

		frappe.db.set_value("RD Item", self.book, "doi_state", "Findable")
		self.assertEqual(get_record(self.book)["doi"], doi)

	def test_settings_are_checked(self):
		s = frappe.get_doc("RD Settings")
		s.doi_enabled, s.doi_prefix = 1, "11.1"
		with self.assertRaises(frappe.ValidationError):
			s.save()


class TestCatalogueFirst(SharingTestCase):
	def test_books_are_listed_first_and_filled_in_later(self):
		from sok_resdesk import ingest

		frappe.db.set_single_value("RD Settings", "book_limit", "No limit")
		rows = [
			{
				"identifier": f"{PREFIX}0094",
				"title": "Quick one",
				"language": "Kannada",
				"imagecount": "88",
				"format": ["OCR Search Text", "Text PDF"],
			},
			{
				"identifier": f"{PREFIX}0095",
				"title": "Quick two",
				"creator": "A. Writer",
				"format": "Text PDF",
			},
		]
		with (
			mock.patch("sok_resdesk.ingest._status", return_value="Running"),
			mock.patch("sok_resdesk.ingest._log"),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
		):
			self.assertFalse(ingest.catalogue_first("run", rows, None))
		one = frappe.db.get_value(
			"RD Item",
			f"{PREFIX}0094",
			["details_pending", "last_ingested", "has_page_text", "page_count", "language"],
			as_dict=True,
		)
		self.assertEqual(
			(one.details_pending, one.last_ingested, one.has_page_text, one.page_count, one.language),
			(1, None, 1, 88, "kan"),
		)
		self.assertFalse(
			ingest._already_done(f"{PREFIX}0094", None, only_new=True)
		)  # its details are still to come

		class FakeIA:
			def metadata(self, identifier):
				return {
					"metadata": {
						"identifier": identifier,
						"title": "Quick one, in full",
						"language": "Kannada",
					},
					"files": [],
				}

		class Buffer:
			def add(self, record, pages, replace_pages=True, if_changed=False):
				return 0

		created, _ = ingest._ingest_one(FakeIA(), f"{PREFIX}0094", None, fetch_text=False, buffer=Buffer())
		self.assertTrue(created)  # new to the run that listed it
		self.assertEqual(
			frappe.db.get_value("RD Item", f"{PREFIX}0094", ["details_pending", "title"]),
			(0, "Quick one, in full"),
		)
		self.assertTrue(ingest._already_done(f"{PREFIX}0094", None, only_new=True))


class TestMetadataFileIngest(SharingTestCase):
	def test_a_collection_catalogued_from_a_file(self):
		from sok_resdesk import ingest

		frappe.db.set_single_value("RD Settings", "book_limit", "No limit")
		full = {
			"metadata": {"identifier": f"{PREFIX}0096", "title": "Complete in the file", "language": "kan"},
			"files": [{"name": f"{PREFIX}0096_hocr_searchtext.txt.gz"}, {"name": f"{PREFIX}0096.pdf"}],
		}
		lines = [
			json.dumps(full),
			json.dumps(
				{"identifier": f"{PREFIX}0097", "title": "Only a search record", "creator": "A. Writer"}
			),
			"garbage",
		]
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "rdtest-books.jsonl",
				"content": "\n".join(lines),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", f.name, force=True))
		name = ingest.ensure_profile(
			"rdtest file", scope_type="Metadata File", metadata_file=f.file_url, fetch_fulltext=0, max_items=0
		)
		profile = frappe.get_doc("RD Ingest Profile", name)
		self.assertEqual(ingest.count_profile(name)["count"], 2)
		run = ingest.create_run(profile, "Manual")
		with (
			mock.patch("sok_resdesk.search.MeiliClient"),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
		):
			batches = ingest.plan_run(run.name, foreground=True)
		# the complete record needs nothing more; the search record still gets its details
		self.assertEqual([i for b in batches for i in b], [f"{PREFIX}0097"])
		one = frappe.db.get_value(
			"RD Item", f"{PREFIX}0096", ["details_pending", "has_page_text", "title"], as_dict=True
		)
		self.assertEqual((one.details_pending, one.has_page_text, one.title), (0, 1, "Complete in the file"))
		self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}0097", "details_pending"), 1)
		log = frappe.db.get_value("RD Ingest Run", run.name, "log")
		self.assertIn("2 records in the metadata file", log)
		self.assertIn("1 lines left out", log)


class TestParallelFirstPass(SharingTestCase):
	def test_the_first_pass_runs_in_parts_ahead_of_the_batches(self):
		from sok_resdesk import ingest

		frappe.db.set_single_value("RD Settings", "book_limit", "No limit")
		rows = [{"identifier": f"{PREFIX}{n:04d}", "title": f"Book {n}"} for n in range(600, 603)]
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "rdtest-parts.jsonl",
				"content": "\n".join(json.dumps(r) for r in rows),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", f.name, force=True))
		name = ingest.ensure_profile(
			"rdtest parts",
			scope_type="Metadata File",
			metadata_file=f.file_url,
			fetch_fulltext=0,
			max_items=0,
		)
		run = ingest.create_run(frappe.get_doc("RD Ingest Profile", name), "Manual")
		with (
			mock.patch.object(ingest, "CATALOGUE_CHUNK", 2),
			mock.patch("sok_resdesk.search.MeiliClient"),
			mock.patch("sok_resdesk.ingest._feed"),
		):
			ingest.plan_run(run.name)  # in the background: parts and batches wait on the run
		waiting = ingest.waiting_batches(run.name)
		self.assertEqual([b[0] for b in waiting[:2]], [ingest.CATALOGUE, ingest.CATALOGUE])  # parts first
		self.assertEqual(sum(len(b) for b in waiting[2:]), 3)  # then the books' own batches
		self.assertFalse(frappe.db.exists("RD Item", f"{PREFIX}0600"))  # nothing catalogued yet
		with mock.patch("sok_resdesk.search.IndexBuffer.flush"), mock.patch("sok_resdesk.ingest._feed"):
			for n, part in enumerate(waiting[:2], start=1):
				ingest.run_batch(run.name, part, batch_no=n)
		self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}0602", "details_pending"), 1)
		self.assertFalse(
			os.listdir(ingest._parts_dir())
			and any(n.startswith(frappe.scrub(run.name)) for n in os.listdir(ingest._parts_dir()))
		)
		self.assertIn(
			"first pass part 1: 2 books catalogued", frappe.db.get_value("RD Ingest Run", run.name, "log")
		)


class TestMachineSettings(SharingTestCase):
	def setUp(self):
		super().setUp()
		self._machine = {
			f: frappe.db.get_single_value("RD Settings", f) for f in ("queue_workers", "max_upload_mb")
		}
		self._max = frappe.db.get_single_value("System Settings", "max_file_size")
		self.addCleanup(self._back)

	def _back(self):
		frappe.db.set_single_value("RD Settings", self._machine)
		frappe.db.set_single_value("System Settings", "max_file_size", self._max)
		frappe.db.commit()

	def test_upload_limit_and_workers_from_settings(self):
		from sok_resdesk import setup

		s = frappe.get_doc("RD Settings")
		s.max_upload_mb = 250
		with mock.patch("sok_resdesk.server.helper_configured", return_value=False):
			s.save()
		self.assertEqual(frappe.db.get_single_value("System Settings", "max_file_size"), 250)
		s = frappe.get_doc("RD Settings")
		s.queue_workers = 6
		with mock.patch("sok_resdesk.server.helper_configured", return_value=False):
			s.save()  # no helper: saved, and the command to run is shown
		self.assertIn("QUEUE_WORKERS=6", str(frappe.message_log))
		s = frappe.get_doc("RD Settings")
		s.queue_workers = 40
		self.assertRaises(frappe.ValidationError, s.save)
		s = frappe.get_doc("RD Settings")
		s.max_upload_mb = 5000
		self.assertRaises(frappe.ValidationError, s.save)
		frappe.db.set_single_value("RD Settings", "max_upload_mb", 0)
		setup.allow_large_uploads()  # empty: the default
		self.assertEqual(frappe.db.get_single_value("System Settings", "max_file_size"), setup.UPLOAD_MB)


class TestLongIdentifierLists(SharingTestCase):
	def test_eighty_thousand_identifiers_are_queued_not_searched(self):
		from sok_resdesk import ingest

		ids = [f"{PREFIX}L{n:05d}" for n in range(80000)]
		name = ingest.ensure_profile(
			"rdtest long list",
			scope_type="Identifier List",
			identifiers="\n".join(ids),
			max_items=0,
			catalogue_first=0,
		)
		profile = frappe.get_doc("RD Ingest Profile", name)
		self.assertEqual(profile.build_query(), "80,000 identifiers listed on the profile")
		self.assertEqual(ingest.count_profile(name)["count"], 80000)  # counted here, not on archive.org
		run = ingest.create_run(profile, "Manual")  # the run's query fits its column
		with mock.patch("sok_resdesk.search.MeiliClient"), mock.patch("sok_resdesk.ingest._feed"):
			ingest.plan_run(run.name)
		row = frappe.db.get_value(
			"RD Ingest Run", run.name, ["total_found", "chunks_total", "status"], as_dict=True
		)
		self.assertEqual(row.total_found, 80000)
		self.assertGreater(row.chunks_total, 1)
		self.assertEqual(row.status, "Running")

	def test_listed_books_get_their_records_a_hundred_at_a_time(self):
		from sok_resdesk import ingest

		class FakeIA:
			def __init__(self):
				self.queries = []

			def iter_records(self, query, limit=0, page_size=5000, fields=""):
				self.queries.append(query)
				for ident in query.removeprefix("identifier:(").removesuffix(")").split(" OR "):
					yield {"identifier": ident, "title": ident.upper()}

		ia = FakeIA()
		ids = [f"b{n}" for n in range(250)]
		with (
			mock.patch("sok_resdesk.ingest._log"),
			mock.patch("sok_resdesk.ingest._status", return_value="Running"),
		):
			records = ingest._records_for_ids(ia, ids, "run", False)
		self.assertEqual(len(ia.queries), 3)  # 100 + 100 + 50
		self.assertEqual(len(records), 250)
		self.assertEqual(records["b7"]["title"], "B7")
