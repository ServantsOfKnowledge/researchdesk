"""0.39: books from OAI-PMH repositories (DSpace, EPrints…), through a whole ingest run. The
repository and its PDFs are stood in for; the catalogue, the run and its batches are real."""

from unittest import mock

import frappe

from sok_resdesk.core import harvest
from sok_resdesk.tests.oai_fixtures import HEAD, Resp, make_pdf, record
from sok_resdesk.tests.test_operations import OpsTestCase

PREFIX = "rdtestrepo"


def listing(*records, token=""):
	return (
		HEAD
		+ "<ListRecords>"
		+ "".join(records)
		+ f"<resumptionToken>{token}</resumptionToken></ListRecords></OAI-PMH>"
	)


IDENTIFY = (
	HEAD + "<Identify><repositoryName>Rdtest University Repository</repositoryName>"
	"<baseURL>https://repo.example.org/oai/request</baseURL><granularity>YYYY-MM-DDThh:mm:ssZ</granularity>"
	"</Identify></OAI-PMH>"
)
BOOK = (
	"<dc:title>ವಚನ ಸಾಹಿತ್ಯ</dc:title><dc:creator>Rdtest Halakatti, P. G.</dc:creator><dc:date>1931</dc:date>"
	"<dc:language>kan</dc:language><dc:identifier>http://hdl.handle.net/123/1</dc:identifier>"
	"<dc:identifier>https://repo.example.org/bitstream/123/1/vachana.pdf</dc:identifier>"
)
THESIS = (
	"<dc:title>A thesis on Haridasa songs</dc:title><dc:type>Thesis</dc:type><dc:date>2019</dc:date>"
	"<dc:language>eng</dc:language><dc:identifier>https://repo.example.org/handle/123/2</dc:identifier>"
)


class Repo:
	"""The repository: answers in turn, whatever is asked (Identify, then the listings)."""

	def __init__(self, *answers):
		self.answers, self.asked, self.headers = list(answers), [], {}

	def get(self, url, params=None, timeout=None):
		self.asked.append(dict(params or {}))
		verb = (params or {}).get("verb")
		if verb == "Identify":
			return Resp(IDENTIFY)
		return Resp(self.answers.pop(0))


class TestRepositorySource(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit"})
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.IndexBuffer.flush"),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
			mock.patch(
				"sok_resdesk.repository.find_pdf",
				return_value="https://repo.example.org/bitstreams/2/download",
			),
			mock.patch("sok_resdesk.repository.download_pdf", side_effect=self.pdf),
		):
			p.start()
			self.addCleanup(p.stop)
		self.pdfs = []
		self.addCleanup(self._clean)
		frappe.cache.delete_value("resdesk:oai-name:https://repo.example.org/oai/request")
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest repository",
				"source": "Repository (OAI-PMH)",
				"oai_url": "https://repo.example.org/oai/request",
				"id_prefix": PREFIX,
				"fetch_fulltext": 1,
				"max_items": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def _clean(self):
		frappe.db.delete("RD Item", {"name": ("like", f"{PREFIX}%")})
		frappe.db.delete("RD Ingest Run", {"profile": self.profile.name})
		frappe.db.delete("RD Ingest Profile", self.profile.name)
		frappe.db.delete("RD Creator", {"name": ("like", "Rdtest%")})
		frappe.db.commit()

	def pdf(self, url):
		self.pdfs.append(url)
		if url.endswith("vachana.pdf"):
			return make_pdf(["First page of the vachana book", "Second page of the vachana book"])
		return make_pdf(["", ""])  # a scan with no text layer

	def run_profile(self, repo):
		from sok_resdesk.ingest import create_run, run_ingest

		with mock.patch(
			"sok_resdesk.repository.harvester",
			return_value=harvest.Harvester(
				self.profile.oai_url, session=repo, delay=0, sleep=lambda _s: None
			),
		):
			run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), "Manual")
			frappe.db.commit()
			run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_harvest_catalogue_text_and_later_changes(self):
		first = self.run_profile(
			Repo(
				listing(
					record("oai:repo.example.org:123/1", BOOK), record("oai:repo.example.org:123/2", THESIS)
				)
			)
		)
		self.assertEqual((first.status, first.created_count), ("Completed", 2), first.log)

		book = frappe.get_doc("RD Item", f"{PREFIX}-123-1")
		self.assertEqual(book.source, "Repository")
		self.assertEqual((book.title, book.year, book.language), ("ವಚನ ಸಾಹಿತ್ಯ", 1931, "kan"))
		self.assertEqual(book.source_url, "http://hdl.handle.net/123/1")
		self.assertEqual(book.remote_pdf, "https://repo.example.org/bitstream/123/1/vachana.pdf")
		self.assertEqual(book.collections, "Rdtest University Repository")
		self.assertTrue(book.has_page_text)
		self.assertEqual((book.page_count, book.text_source), (2, "PDF text layer"))
		from sok_resdesk.ingest import fetch_pages

		self.assertEqual(fetch_pages(book.name)[1]["text"], "Second page of the vachana book")

		# the thesis named no PDF: found on its web page; a scan with no text is catalogued without
		thesis = frappe.get_doc("RD Item", f"{PREFIX}-123-2")
		self.assertEqual(thesis.item_type, "Thesis")
		self.assertEqual(thesis.remote_pdf, "https://repo.example.org/bitstreams/2/download")
		self.assertFalse(thesis.has_page_text)
		self.assertEqual(thesis.text_source, "PDF without text (scan)")

		from sok_resdesk.catalogue import item_to_record

		rec = item_to_record(book)
		self.assertEqual(rec["pdf_url"], book.remote_pdf)
		self.assertFalse(rec["on_archive_org"])

		# the next run asks only for what changed since; a deleted record leaves the portal
		stamp = frappe.db.get_value("RD Ingest Profile", self.profile.name, "harvested_until")
		self.assertTrue(stamp)
		repo = Repo(listing(record("oai:repo.example.org:123/2", deleted=True)))
		second = self.run_profile(repo)
		self.assertEqual(repo.asked[1].get("from"), stamp)
		self.assertEqual(second.status, "Completed", second.log)
		self.assertEqual(
			frappe.db.get_value("RD Item", f"{PREFIX}-123-2", ["published", "removed_from_source"]), (0, 1)
		)
		self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}-123-1", "published"), 1)

	def test_unchanged_records_are_not_fetched_again(self):
		listed = listing(record("oai:repo.example.org:123/1", BOOK))
		self.run_profile(Repo(listed))
		self.assertEqual(len(self.pdfs), 1)
		frappe.db.set_value("RD Ingest Profile", self.profile.name, "update_existing", 1)  # harvest all again
		again = self.run_profile(Repo(listed))
		self.assertEqual((again.created_count, again.skipped_count), (0, 0), again.log)
		self.assertEqual(again.updated_count, 1)  # Refresh: read again on purpose
		frappe.db.set_value(
			"RD Ingest Profile", self.profile.name, {"update_existing": 0, "harvested_until": ""}
		)
		third = self.run_profile(Repo(listed))
		self.assertEqual(third.skipped_count, 1, third.log)  # same datestamp: nothing to do
		self.assertEqual(len(self.pdfs), 2)

	def test_profile_defaults(self):
		doc = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest repository 2",
				"source": "Repository (OAI-PMH)",
				"oai_url": "https://www.dspace.kud.ac.in/server/oai/request",
			}
		).insert(ignore_permissions=True)
		self.assertEqual((doc.id_prefix, doc.oai_prefix), ("kud", "oai_dc"))
		self.assertIn("records at https://www.dspace.kud.ac.in", doc.build_query())
		frappe.db.delete("RD Ingest Profile", doc.name)
