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
			def add(self, record, pages, replace_pages=True):
				return 0

		created, _ = ingest._ingest_one(FakeIA(), f"{PREFIX}0094", None, fetch_text=False, buffer=Buffer())
		self.assertTrue(created)  # new to the run that listed it
		self.assertEqual(
			frappe.db.get_value("RD Item", f"{PREFIX}0094", ["details_pending", "title"]),
			(0, "Quick one, in full"),
		)
		self.assertTrue(ingest._already_done(f"{PREFIX}0094", None, only_new=True))
