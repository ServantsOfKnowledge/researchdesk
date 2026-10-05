"""0.61: the OPDS catalogue for e-reader apps, over real items (no network)."""

from xml.etree import ElementTree as ET

import frappe

from sok_resdesk import opds
from sok_resdesk.tests.test_operations import OpsTestCase, _item

NS = {"a": "http://www.w3.org/2005/Atom"}
ACQ = "http://opds-spec.org/acquisition/open-access"


class TestOpds(OpsTestCase):
	def setUp(self):
		super().setUp()
		self.open_book, self.shut_book = _item(71), _item(72)
		frappe.db.set_value(
			"RD Item",
			self.open_book,
			{
				"published": 1,
				"visibility": "Public",
				"source": "Local",
				"access_status": "Open",
				"local_pdf": "a.pdf",
				"local_files": "a.epub",
				"title": "Rdtest Opds Open",
			},
		)
		frappe.db.set_value(
			"RD Item",
			self.shut_book,
			{
				"published": 1,
				"visibility": "Public",
				"source": "Local",
				"access_status": "Restricted",
				"local_pdf": "b.pdf",
				"title": "Rdtest Opds Shut",
			},
		)
		frappe.db.commit()

	def feed(self, path, **args):
		resp = opds.route(path, args)
		self.assertEqual(resp.status_code, 200, path)
		return ET.fromstring(resp.get_data(as_text=True))

	def entries(self, root):
		return {e.find("a:title", NS).text: e for e in root.findall("a:entry", NS)}

	def test_the_start_lists_the_feeds(self):
		titles = [e.find("a:title", NS).text for e in self.feed("/opds").findall("a:entry", NS)]
		self.assertEqual(titles, ["Newest books", "Collections"])

	def test_new_books_have_downloads_only_when_a_reader_may_have_them(self):
		found = self.entries(self.feed("/opds/new"))
		links = lambda e: [  # noqa: E731
			link.get("href") for link in e.findall("a:link", NS) if link.get("rel") == ACQ
		]
		self.assertEqual(len(links(found["Rdtest Opds Open"])), 2)
		self.assertIn("name=a.epub", "".join(links(found["Rdtest Opds Open"])))
		self.assertEqual(links(found["Rdtest Opds Shut"]), [])

	def test_search_finds_by_title(self):
		found = self.entries(self.feed("/opds/search", q="Rdtest Opds Shut"))
		self.assertEqual(list(found), ["Rdtest Opds Shut"])

	def test_unknown_addresses_are_not_found(self):
		self.assertEqual(opds.route("/opds/nothing", {}).status_code, 404)
		self.assertEqual(opds.route("/opds/collection/rdtest-none", {}).status_code, 404)
		self.assertIsNone(opds.route("/elsewhere", {}))
