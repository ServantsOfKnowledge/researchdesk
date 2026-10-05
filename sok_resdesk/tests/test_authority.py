"""Integration tests for 0.36, authority control: authors matched to Wikidata (and VIAF), subjects
to LCSH, what a match changes (MARC, JSON-LD, the person's page), merging two names. Wikidata
and id.loc.gov are stood in for."""

import json
from unittest import mock

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase, _item


def _t(t):
	return {"mainsnak": {"datavalue": {"value": {"time": t}}}}


ENTITIES = {
	"entities": {
		"Q2724213": {
			"labels": {"en": {"value": "Rdtest Purandara Dasa"}},
			"descriptions": {"en": {"value": "Indian composer"}},
			"aliases": {},
			"claims": {
				"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
				"P569": [_t("+1484-00-00T00:00:00Z")],
				"P570": [_t("+1564-00-00T00:00:00Z")],
				"P214": [{"mainsnak": {"datavalue": {"value": "100219138"}}}],
			},
		}
	}
}
LCSH = {"hits": [{"uri": "http://id.loc.gov/authorities/subjects/sh85061212", "aLabel": "India--History"}]}


def fake_http(url):
	if "wbsearchentities" in url:
		return {"search": [{"id": "Q2724213", "label": "Rdtest Purandara Dasa"}]}
	if "wbgetentities" in url:
		return ENTITIES
	if "suggest2" in url:
		return LCSH
	raise AssertionError(url)


class AuthorityTestCase(OpsTestCase):
	def setUp(self):
		super().setUp()
		for target in ("sok_resdesk.authority._http_json",):
			p = mock.patch(target, side_effect=fake_http)
			p.start()
			self.addCleanup(p.stop)
		p = mock.patch("sok_resdesk.authority.PAUSE", 0)
		p.start()
		self.addCleanup(p.stop)
		self._auto = frappe.db.get_single_value("RD Settings", "authority_auto_accept")
		self.addCleanup(self._back)

	def _back(self):
		frappe.db.set_single_value("RD Settings", "authority_auto_accept", self._auto)
		frappe.db.delete("RD Creator", {"name": ("like", "Rdtest%")})
		frappe.db.delete("RD Subject", {"name": ("like", "Rdtest%")})
		frappe.db.commit()

	def _book_by(self, n, creator, subject=None):
		item = _item(n)
		doc = frappe.get_doc("RD Item", item)
		doc.set("creators", [])
		doc.append("creators", {"creator": self._creator(creator), "name_as_given": creator})
		if subject:
			if not frappe.db.exists("RD Subject", subject):
				frappe.get_doc({"doctype": "RD Subject", "subject_name": subject}).insert(
					ignore_permissions=True
				)
			doc.set("subjects", [{"subject": subject}])
		doc.flags.skip_search_index = True
		doc.save(ignore_permissions=True)
		return item

	def _creator(self, name):
		if not frappe.db.exists("RD Creator", name):
			frappe.get_doc({"doctype": "RD Creator", "full_name": name}).insert(ignore_permissions=True)
		return name


class TestMatching(AuthorityTestCase):
	def test_proposed_then_accepted_and_what_it_changes(self):
		from sok_resdesk import authority
		from sok_resdesk.catalogue import get_record
		from sok_resdesk.core import citations, marc

		item = self._book_by(1, "Rdtest Purandaradasa")
		frappe.db.set_single_value("RD Settings", "authority_auto_accept", 0)
		self.assertEqual(authority.match_creator("Rdtest Purandaradasa"), "proposed")
		self.assertEqual(
			frappe.db.get_value("RD Creator", "Rdtest Purandaradasa", "match_status"), "Proposed"
		)
		data = authority.overview("creator", "Proposed", "Rdtest")
		row = next(r for r in data["rows"] if r.name == "Rdtest Purandaradasa")
		self.assertEqual(row.candidates[0]["id"], "Q2724213")
		self.assertEqual(row.books, 1)

		out = authority.accept("creator", "Rdtest Purandaradasa", "Q2724213")
		self.assertTrue(out["ok"])
		c = frappe.db.get_value(
			"RD Creator",
			"Rdtest Purandaradasa",
			["wikidata_id", "viaf_id", "born", "died", "match_status"],
			as_dict=True,
		)
		self.assertEqual(
			(c.wikidata_id, c.viaf_id, c.born, c.died, c.match_status),
			("Q2724213", "100219138", 1484, 1564, "Confirmed"),
		)

		record = get_record(item)
		self.assertEqual(record["creator_ids"][0], {"wikidata": "Q2724213", "viaf": "100219138"})
		ld = citations.json_ld(record, "http://x")
		self.assertIn("http://www.wikidata.org/entity/Q2724213", ld["author"][0]["sameAs"])
		xml = marc.to_marcxml_record(record, "http://x")
		self.assertIn("http://viaf.org/viaf/100219138", xml)
		self.assertIn("http://www.wikidata.org/entity/Q2724213", xml)
		self.assertEqual([b.item_id for b in authority.creator_books("Q2724213")], [item])

		authority.undo("creator", "Rdtest Purandaradasa")
		self.assertFalse(frappe.db.get_value("RD Creator", "Rdtest Purandaradasa", "wikidata_id"))
		authority.reject("creator", "Rdtest Purandaradasa")
		self.assertEqual(
			frappe.db.get_value("RD Creator", "Rdtest Purandaradasa", "match_status"), "No match"
		)

	def test_near_certain_matches_accepted_only_when_allowed(self):
		from sok_resdesk import authority

		self._book_by(2, "Rdtest Purandara Dasa")
		self.assertEqual(authority.match_creator("Rdtest Purandara Dasa", auto=False), "proposed")
		self.assertEqual(authority.match_creator("Rdtest Purandara Dasa", auto=True), "auto")
		self.assertEqual(
			frappe.db.get_value("RD Creator", "Rdtest Purandara Dasa", "wikidata_id"), "Q2724213"
		)

	def test_two_names_for_one_person_are_merged(self):
		from sok_resdesk import authority

		a = self._book_by(3, "Rdtest Purandara Dasa")
		b = self._book_by(4, "Rdtest Purandaradasa")
		for name in ("Rdtest Purandara Dasa", "Rdtest Purandaradasa"):
			authority.search_again("creator", name, "Q2724213")
		authority.accept("creator", "Rdtest Purandara Dasa", "Q2724213")
		out = authority.accept("creator", "Rdtest Purandaradasa", "Q2724213")
		self.assertEqual([s.name for s in out["same_person"]], ["Rdtest Purandara Dasa"])
		authority.merge("Rdtest Purandaradasa", "Rdtest Purandara Dasa")
		self.assertFalse(frappe.db.exists("RD Creator", "Rdtest Purandaradasa"))
		for item in (a, b):
			row = frappe.get_doc("RD Item", item).creators[0]
			self.assertEqual(row.creator, "Rdtest Purandara Dasa")
		# each book keeps the name as printed
		self.assertEqual(frappe.get_doc("RD Item", b).creators[0].name_as_given, "Rdtest Purandaradasa")

	def test_subjects_to_lcsh(self):
		from sok_resdesk import authority
		from sok_resdesk.catalogue import get_record
		from sok_resdesk.core import marc

		item = self._book_by(5, "Rdtest Someone", subject="Rdtest History -- India")
		self.assertIn(authority.match_subject("Rdtest History -- India"), ("proposed", "none"))
		authority.search_again("subject", "Rdtest History -- India", "India history")
		authority.accept("subject", "Rdtest History -- India", "sh85061212")
		xml = marc.to_marcxml_record(get_record(item), "http://x")
		self.assertIn('tag="650"', xml)
		self.assertIn("http://id.loc.gov/authorities/subjects/sh85061212", xml)
		self.assertIn("India--History", xml)

	def test_unknown_candidates_are_refused(self):
		from sok_resdesk import authority

		self._creator("Rdtest Nobody")
		frappe.db.set_value("RD Creator", "Rdtest Nobody", "match_candidates", json.dumps([]))
		self.assertRaises(frappe.ValidationError, authority.accept, "creator", "Rdtest Nobody", "Q1")
