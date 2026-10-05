"""0.42: a library system's catalogue matched to the books here, and the links sent back. Koha
and the search engine are stood in for; the catalogue, the records and the decisions are real."""

from unittest import mock

import frappe

from sok_resdesk.core import marcin
from sok_resdesk.tests.libsys_fixtures import KOHA_XML
from sok_resdesk.tests.test_operations import OpsTestCase


class FakeKoha:
	def __init__(self):
		self.updated = {}

	def get(self, biblio_id):
		recs = {marcin.record_id(r): r for r in marcin.read(KOHA_XML.encode())}
		return marcin.collection_xml([recs[biblio_id]])

	def update(self, biblio_id, marcxml):
		self.updated[biblio_id] = marcxml


class TestLibrarySystems(OpsTestCase):
	def setUp(self):
		super().setUp()
		from sok_resdesk.catalogue import upsert_item
		from sok_resdesk.core.normalize import normalize_ia_item

		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit"})
		for p in (
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
			mock.patch(
				"sok_resdesk.librarysystems._search_titles", side_effect=lambda t: ["rdtestlib-vachana"]
			),
		):
			p.start()
			self.addCleanup(p.stop)
		upsert_item(
			normalize_ia_item(
				"rdtestlib-vachana",
				{
					"title": "ವಚನ ಸಾಹಿತ್ಯ",
					"creator": ["Rdtest Halakatti, P. G."],
					"date": "1931",
					"language": "kan",
				},
				[],
			)
		)
		upsert_item(normalize_ia_item("rdtestlib-linked", {"title": "A thesis on Haridasa songs"}, []))
		f = frappe.get_doc(
			{"doctype": "File", "file_name": "rdtest-koha.xml", "content": KOHA_XML, "is_private": 1}
		).insert(ignore_permissions=True)
		self.system = frappe.get_doc(
			{
				"doctype": "RD Library System",
				"system_name": "rdtest Koha",
				"system_type": "Koha",
				"source_kind": "MARC File",
				"marc_file": f.file_url,
				"opac_url": "https://opac.example.org/cgi-bin/koha/opac-detail.pl?biblionumber={id}",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._clean, f.name)

	def _clean(self, file_name):
		frappe.db.delete("RD Library Record", {"library_system": self.system.name})
		frappe.db.delete("RD Library System", self.system.name)
		frappe.db.delete("RD Item", {"name": ("like", "rdtestlib%")})
		frappe.db.delete("RD Item", {"name": ("like", "rdtest-koha%")})
		frappe.db.delete("RD Creator", {"name": ("like", "Rdtest%")})
		frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def records(self):
		return {
			r.record_id: r
			for r in frappe.get_all(
				"RD Library Record",
				filters={"library_system": self.system.name},
				fields=["name", "record_id", "status", "item", "why", "title"],
			)
		}

	def test_import_match_decide_and_send_back(self):
		from sok_resdesk import librarysystems

		result = librarysystems.import_records(self.system.name)
		self.assertEqual((result["records"], result["new"]), (2, 2))
		recs = self.records()
		# its 856 already points to the archive.org book here: certain
		self.assertEqual((recs["4513"].status, recs["4513"].item), ("Linked", "rdtestlib-linked"))
		# the same title, author and year in Kannada: linked
		self.assertEqual((recs["4512"].status, recs["4512"].item), ("Linked", "rdtestlib-vachana"))
		self.assertEqual(recs["4512"].title, "ವಚನ ಸಾಹಿತ್ಯ")

		# a cataloguer's decision is kept when the catalogue is imported again
		librarysystems.decide(recs["4512"].name, not_a_match=1)
		librarysystems.import_records(self.system.name)
		self.assertEqual(self.records()["4512"].status, "Not This Book")
		librarysystems.decide(recs["4512"].name, item="rdtestlib-vachana")

		# the book page links to the library's record
		links = librarysystems.catalogue_links("rdtestlib-vachana")
		self.assertEqual(
			links[0]["url"], "https://opac.example.org/cgi-bin/koha/opac-detail.pl?biblionumber=4512"
		)

		# links sent back into Koha: only what each record lacks
		target = frappe.get_doc(
			{
				"doctype": "RD Push Target",
				"target_name": "rdtest libsys koha",
				"target_type": "Koha",
				"koha_url": "https://koha.example.org",
				"scope": "Everything",
				"enabled": 1,
				"dry_run": 0,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.delete("RD Push Target", target.name))
		frappe.db.set_value("RD Library System", self.system.name, "push_target", target.name)
		koha = FakeKoha()
		with mock.patch("sok_resdesk.outbound._client", return_value=koha):
			sent = librarysystems.send_back(self.system.name)
		self.assertEqual(sent, {"sent": 2, "failed": 0})
		back = next(marcin.read(koha.updated["4512"].encode()))
		self.assertIn("/library/item/rdtestlib-vachana", " ".join(marcin.links(back)))
		self.assertEqual(marcin.summary(back)["title"], "ವಚನ ಸಾಹಿತ್ಯ")  # their record, untouched otherwise
		with mock.patch("sok_resdesk.outbound._client", return_value=koha):
			self.assertEqual(librarysystems.send_back(self.system.name), {"sent": 0, "failed": 0})  # once

		# for any other system: the records with their links, to import there
		librarysystems.download_with_links(self.system.name)
		out = list(marcin.read(frappe.response["filecontent"].encode()))
		self.assertEqual(len(out), 2)
		self.assertTrue(all(any("/library/item/" in u for u in marcin.links(r)) for r in out))

	def test_records_with_no_match_can_be_catalogued(self):
		from sok_resdesk import librarysystems

		frappe.db.set_value("RD Library System", self.system.name, "catalogue_unmatched", 1)
		with mock.patch("sok_resdesk.librarysystems._search_titles", return_value=[]):
			frappe.db.delete("RD Item", {"name": "rdtestlib-vachana"})
			librarysystems.import_records(self.system.name)
		rec = self.records()["4512"]
		self.assertEqual(rec.status, "Catalogued")
		item = frappe.get_doc("RD Item", rec.item)
		self.assertEqual((item.source, item.title, item.year), ("Library System", "ವಚನ ಸಾಹಿತ್ಯ", 1931))
		self.assertIn("biblionumber=4512", item.source_url)
