"""0.59: sending a photograph to Wikimedia Commons under the sender's own account.
Commons is stood in for; the item, its original file, the account and the checks are real."""

import os
from unittest import mock

import frappe

from sok_resdesk import commons, wikimedia
from sok_resdesk.tests.test_photographs import PHOTO, PhotoBase

LICENCE = "https://creativecommons.org/licenses/by-sa/4.0/"
TOKEN = "t" * 40


class FakeCommons:
	"""A Commons that records what it is given and answers what a plan asks."""

	def __init__(self, duplicate=(), taken=False, missing=(), rights=("edit", "upload")):
		self.duplicate, self.taken, self.missing, self.rights = list(duplicate), taken, list(missing), rights
		self.uploaded, self.edits = [], []

	def whoami(self):
		return {"name": "Volunteer", "id": 1, "rights": list(self.rights), "groups": []}

	def csrf(self):
		return "T"

	def get(self, **p):
		if p.get("list") == "allimages":
			return {"query": {"allimages": [{"name": n} for n in self.duplicate]}}
		titles = p["titles"].split("|")
		pages = []
		for t in titles:
			if t.startswith("File:"):
				pages.append(
					{"title": t, **({"pageid": 99} if self.taken or self.uploaded else {"missing": True})}
				)
			else:
				pages.append(
					{
						"title": t,
						**({"missing": True} if t.split(":", 1)[1] in self.missing else {"pageid": 5}),
					}
				)
		return {"query": {"pages": pages}}

	def upload(self, filename, path, text, comment):
		self.uploaded.append((filename, os.path.getsize(path), text))
		return {"result": "Success"}

	def post(self, **d):
		self.edits.append(d)
		return {"success": 1}


class TestCommons(PhotoBase):
	def setUp(self):
		super().setUp()
		self.run_profile(self.photos)
		frappe.db.set_value(
			"RD Item",
			PHOTO,
			{"licence_url": LICENCE, "creator_display": "A. Photographer", "access_status": "Open"},
		)
		frappe.db.delete(wikimedia.DOCTYPE, {"name": "Administrator"})
		acc = frappe.new_doc(wikimedia.DOCTYPE)
		acc.update({"user": "Administrator", "wikimedia_user": "Volunteer", "token": TOKEN})
		acc.flags.ignore_permissions = True
		acc.insert()
		self.addCleanup(
			lambda: frappe.delete_doc(wikimedia.DOCTYPE, "Administrator", force=True, ignore_permissions=True)
		)
		frappe.db.commit()

	def api(self, **kw):
		fake = FakeCommons(**kw)
		p = mock.patch("sok_resdesk.commons._client", return_value=fake)
		p.start()
		self.addCleanup(p.stop)
		return fake

	def test_the_plan_shows_what_would_be_sent(self):
		self.api()
		p = commons.plan(PHOTO, categories="Rathas")
		self.assertEqual(p["problem"], "")
		self.assertEqual(
			(p["licence"], p["author"], p["site"]),
			("CC BY-SA 4.0", "A. Photographer", "commons.wikimedia.org"),
		)
		self.assertTrue(p["filename"].endswith(".jpg"))
		self.assertIn("{{Cc-by-sa-4.0}}", p["wikitext"])
		self.assertIn("[[Category:Rathas]]", p["wikitext"])
		self.assertEqual([d["qid"] for d in p["depicts"]], ["Q1234"])
		self.assertEqual((p["duplicate"], p["name_taken"], p["missing_categories"]), ([], False, []))

	def test_what_stops_it_is_said_before_anything_is_sent(self):
		self.api()
		frappe.db.set_value(
			"RD Item", PHOTO, "licence_url", "https://creativecommons.org/licenses/by-nc/4.0/"
		)
		self.assertIn("free licences", commons.plan(PHOTO)["problem"])
		frappe.db.set_value("RD Item", PHOTO, {"licence_url": LICENCE, "creator_display": ""})
		self.assertIn("photographer", commons.plan(PHOTO)["problem"])
		frappe.db.set_value("RD Item", PHOTO, {"creator_display": "X", "access_status": "Restricted"})
		self.assertIn("not open", commons.plan(PHOTO)["problem"])

	def test_a_token_that_cannot_upload_is_told_so(self):
		self.api(rights=("edit",))
		self.assertIn("Upload new files", commons.plan(PHOTO)["problem"])

	def test_a_duplicate_a_taken_name_and_a_missing_category_stop_the_send(self):
		self.api(duplicate=["Same.jpg"])
		with self.assertRaisesRegex(frappe.ValidationError, "already has this file"):
			commons.send(PHOTO, "A name.jpg", confirmed=1)
		self.api(taken=True)
		with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
			commons.send(PHOTO, "A name.jpg", confirmed=1)
		self.api(missing=["Nowhere"])
		with self.assertRaisesRegex(frappe.ValidationError, "do not exist"):
			commons.send(PHOTO, "A name.jpg", categories="Nowhere", confirmed=1)

	def test_nothing_is_sent_without_the_confirmation(self):
		fake = self.api()
		with self.assertRaisesRegex(frappe.ValidationError, "Confirm"):
			commons.send(PHOTO, "A name.jpg")
		self.assertEqual(fake.uploaded, [])

	def test_the_reviewed_photograph_is_sent_with_depicts_and_remembered(self):
		fake = self.api()
		res = commons.send(PHOTO, "Ratha at dusk, Udupi.jpg", "A ratha at dusk", "Rathas", confirmed=1)
		self.assertEqual(res["file"], "Ratha at dusk, Udupi.jpg")
		self.assertEqual(res["depicts"], "added")
		name, size, text = fake.uploaded[0]
		self.assertGreater(size, 0)
		self.assertIn("A ratha at dusk", text)
		self.assertEqual((fake.edits[0]["action"], fake.edits[0]["id"]), ("wbeditentity", "M99"))
		self.assertIn("Q1234", fake.edits[0]["data"])
		self.assertEqual(frappe.db.get_value("RD Item", PHOTO, "commons_file"), "Ratha at dusk, Udupi.jpg")
		self.assertEqual(frappe.db.get_value("RD Item", PHOTO, "commons_sent_by"), "Volunteer")
		self.assertIn("Already sent", commons.plan(PHOTO)["problem"])
		with self.assertRaises(frappe.ValidationError):
			commons.send(PHOTO, "Again.jpg", confirmed=1)
