"""0.65: SRU 1.2 over real items (no network)."""

from xml.etree import ElementTree as ET

import frappe

from sok_resdesk import sru
from sok_resdesk.tests.test_operations import OpsTestCase, _item

S = "{http://www.loc.gov/zing/srw/}"


class TestSru(OpsTestCase):
	def setUp(self):
		super().setUp()
		self.a, self.b = _item(81), _item(82)
		frappe.db.set_value(
			"RD Item",
			self.a,
			{"published": 1, "visibility": "Public", "title": "Rdtest Sru Alpha", "year": 1880},
		)
		frappe.db.set_value(
			"RD Item",
			self.b,
			{"published": 1, "visibility": "Public", "title": "Rdtest Sru Beta", "year": 1950},
		)
		frappe.db.commit()

	def run_query(self, **args):
		resp = sru.route(args)
		self.assertEqual(resp.status_code, 200)
		return ET.fromstring(resp.get_data(as_text=True))

	def titles(self, root):
		return sorted(
			t.text
			for t in root.iter("{http://www.loc.gov/MARC21/slim}subfield")
			if t.get("code") == "a" and t.text
		)

	def test_no_arguments_gives_the_explain_record(self):
		root = self.run_query()
		self.assertTrue(root.tag.endswith("explainResponse"))
		titles = [e.text for e in root.iter("{http://explain.z3950.org/dtd/2.0/}title")]
		self.assertIn("creator", titles)

	def test_a_title_search_returns_marcxml_records(self):
		root = self.run_query(query='title = "Rdtest Sru"', maximumRecords="10")
		self.assertEqual(root.find(f"{S}numberOfRecords").text, "2")
		self.assertIn("Rdtest Sru Alpha", self.titles(root))
		self.assertEqual(
			root.find(f"{S}records/{S}record/{S}recordSchema").text, "info:srw/schema/1/marcxml-v1.1"
		)

	def test_boolean_search_and_paging(self):
		root = self.run_query(query='title = "Rdtest Sru" and date = 1950')
		self.assertEqual(root.find(f"{S}numberOfRecords").text, "1")
		root = self.run_query(query='title = "Rdtest Sru"', maximumRecords="1")
		self.assertEqual(root.find(f"{S}nextRecordPosition").text, "2")
		root = self.run_query(query='title = "Rdtest Sru"', maximumRecords="1", startRecord="2")
		self.assertIsNone(root.find(f"{S}nextRecordPosition"))

	def test_dublin_core_records_on_request(self):
		root = self.run_query(query='title = "Rdtest Sru Beta"', recordSchema="dc")
		self.assertIn("Rdtest Sru Beta", ET.tostring(root, encoding="unicode"))
		self.assertIn("oai_dc", ET.tostring(root, encoding="unicode"))

	def test_mistakes_are_diagnostics_not_errors(self):
		for args, number in (
			({"operation": "searchRetrieve"}, "7"),
			({"query": "colour = red"}, "16"),
			({"query": "title = (a"}, "10"),
			({"query": "title = a", "recordSchema": "mods"}, "66"),
			({"query": 'title = "Rdtest Sru"', "startRecord": "500"}, "61"),
			({"operation": "scan"}, "6"),
		):
			root = self.run_query(**args)
			self.assertIn(f"info:srw/diagnostic/1/{number}", ET.tostring(root, encoding="unicode"), args)
