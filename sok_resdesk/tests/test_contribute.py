"""Integration tests for 0.38, giving back to the authorities: names and author links worked out
from the library's matches, QuickStatements, sending through a Wikidata Push Target (dry run and
for real, Wikidata stood in for), subjects for SACO."""

from unittest import mock

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase, _item

PERSON, BOOK = "Q2724213", "Q55555"
ENTITIES = {
	"entities": {
		PERSON: {"labels": {"en": {"value": "Purandara Dasa"}}, "aliases": {}, "claims": {}},
		BOOK: {
			"labels": {"kn": {"value": "ಕೀರ್ತನೆಗಳು"}},
			"aliases": {},
			"claims": {"P2093": [{"mainsnak": {"datavalue": {"value": "ರ್ಡ್ಟೆಸ್ಟ್ ಪುರಂದರದಾಸ"}}}]},
		},
	}
}


class FakeWikidata:
	def __init__(self):
		self.edits = []

	def login(self):
		return "bot"

	def edit(self, qid, data, summary):
		self.edits.append((qid, data, summary))


class TestGivingBack(OpsTestCase):
	def setUp(self):
		super().setUp()
		p = mock.patch("sok_resdesk.contribute._http_json", return_value=ENTITIES)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(self._back)
		frappe.cache.delete_value("resdesk:contribute:plan")
		name = "Rdtest ಪುರಂದರದಾಸ"
		frappe.get_doc(
			{
				"doctype": "RD Creator",
				"full_name": name,
				"wikidata_id": PERSON,
				"match_status": "Confirmed",
			}
		).insert(ignore_permissions=True)
		self.item = _item(1)
		doc = frappe.get_doc("RD Item", self.item)
		doc.language = "kan"
		doc.set("creators", [{"creator": name, "name_as_given": "ರ್ಡ್ಟೆಸ್ಟ್ ಪುರಂದರದಾಸ"}])
		doc.flags.skip_search_index = True
		doc.save(ignore_permissions=True)
		self.target = frappe.get_doc(
			{
				"doctype": "RD Push Target",
				"target_name": "rdtest wikidata",
				"target_type": "Wikidata",
				"wd_user": "bot",
				"scope": "Everything",
				"enabled": 1,
				"dry_run": 1,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "RD External Record",
				"item": self.item,
				"target": self.target.name,
				"external_id": BOOK,
			}
		).insert(ignore_permissions=True)

	def _back(self):
		frappe.db.delete("RD Creator", {"name": ("like", "Rdtest%")})
		frappe.db.delete("RD External Record", {"item": self.item})
		frappe.cache.delete_value("resdesk:contribute:plan")
		frappe.cache.delete_value("resdesk:contribute:last-send")
		frappe.db.commit()

	def test_plan_quickstatements_and_sending(self):
		from sok_resdesk import contribute

		plan = contribute.build_plan()
		kinds = {(e["kind"], e["qid"]) for e in plan["edits"]}
		self.assertIn(("label", PERSON), kinds)  # a Kannada name for someone with only English
		self.assertIn(("author", BOOK), kinds)  # the book item gets its author linked
		label = next(e for e in plan["edits"] if e["kind"] == "label")
		self.assertEqual(label["lang"], "kn")
		author = next(e for e in plan["edits"] if e["kind"] == "author")
		self.assertEqual(author["person"], PERSON)
		self.assertTrue(author["source_url"].endswith(f"/library/item/{self.item}"))

		contribute.quickstatements()
		qs = frappe.response["filecontent"]
		self.assertIn(f"{BOOK}\tP50\t{PERSON}\tP1932", qs)
		self.assertIn(f"{PERSON}\tLkn\t", qs)

		# a dry-run target only counts
		dry = contribute.run_send(self.target.name)
		self.assertTrue(dry["dry_run"])
		self.assertEqual(dry["items"], 2)

		# for real (Wikidata stood in for): one edit per item, then the plan is worked out again
		frappe.db.set_value("RD Push Target", self.target.name, "dry_run", 0)
		fake = FakeWikidata()
		with mock.patch("sok_resdesk.outbound._client", return_value=fake):
			sent = contribute.run_send(self.target.name)
		self.assertEqual((sent["items"], sent["failed"]), (2, 0))
		self.assertEqual({q for q, _d, _s in fake.edits}, {PERSON, BOOK})
		book_data = next(d for q, d, _s in fake.edits if q == BOOK)
		self.assertEqual(book_data["claims"][0]["mainsnak"]["property"], "P50")
		self.assertIsNone(frappe.cache.get_value("resdesk:contribute:plan"))
		self.assertEqual(contribute.plan()["last_send"]["edits"], sent["edits"])

	def test_subjects_for_saco(self):
		from sok_resdesk import contribute

		if not frappe.db.exists("RD Subject", "Rdtest Haridasa literature"):
			frappe.get_doc({"doctype": "RD Subject", "subject_name": "Rdtest Haridasa literature"}).insert(
				ignore_permissions=True
			)
		doc = frappe.get_doc("RD Item", self.item)
		doc.set("subjects", [{"subject": "Rdtest Haridasa literature"}])
		doc.flags.skip_search_index = True
		doc.save(ignore_permissions=True)
		frappe.db.set_value("RD Subject", "Rdtest Haridasa literature", "match_status", "No match")
		contribute.saco()
		self.assertIn("Rdtest Haridasa literature,1,", frappe.response["filecontent"])
		frappe.db.delete("RD Subject", {"name": "Rdtest Haridasa literature"})
