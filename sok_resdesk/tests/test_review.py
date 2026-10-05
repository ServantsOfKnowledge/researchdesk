"""Integration tests for 0.37, the cataloguer's review queue: books checked, questions closing
themselves when the record is corrected, answers that stick, duplicates."""

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase, _item


class TestReviewQueue(OpsTestCase):
	def setUp(self):
		super().setUp()
		self._clean()

	def tearDown(self):
		super().tearDown()  # rolls back; the scan commits, so take its flags out after
		self._clean()

	def _clean(self):
		frappe.db.delete("RD Review Flag", {"item": ("like", "rdtest%")})
		frappe.db.commit()

	def _flags(self, item, status="Open"):
		return set(frappe.get_all("RD Review Flag", filters={"item": item, "status": status}, pluck="check"))

	def test_questions_open_close_and_stay_answered(self):
		from sok_resdesk import review

		item = _item(1)
		frappe.db.set_value("RD Item", item, {"year": 0, "language": "und", "published": 1})
		review.scan([item])
		self.assertTrue({"no_year", "no_language", "no_subjects"} <= self._flags(item))

		# corrected right on the queue's page: kept through re-ingest, questions closed at once
		review.save(item, {"year": "1950", "language": "eng"})
		self.assertEqual(frappe.db.get_value("RD Item", item, "year"), 1950)
		self.assertEqual(frappe.db.get_value("RD Item", item, "lock_metadata"), 1)
		self.assertNotIn("no_year", self._flags(item))
		self.assertIn("no_year", self._flags(item, "Fixed"))

		# "This is right" is not asked again
		flag = frappe.db.get_value("RD Review Flag", {"item": item, "check": "no_subjects"})
		review.ignore(flag)
		review.scan([item])
		self.assertNotIn("no_subjects", self._flags(item))
		self.assertEqual(frappe.db.get_value("RD Review Flag", flag, "status"), "Ignored")

		data = review.overview(q=item)
		self.assertEqual(data["counts"]["no_year"] >= 0, True)

	def test_wrong_script_and_duplicates(self):
		from sok_resdesk import review

		a, b = _item(2), _item(3)
		for item in (a, b):
			frappe.db.set_value(
				"RD Item",
				item,
				{"title": "ರಾಮಾಯಣ ದರ್ಶನಂ rdtest", "language": "eng", "year": 1950, "published": 1},
			)
		review.scan([a, b])
		self.assertIn("language_script", self._flags(a))
		self.assertIn("duplicate", self._flags(a))
		data = review.overview(check="duplicate", q="rdtest")
		row = next(r for r in data["rows"] if r["item_id"] == a)
		dup = next(f for f in row["flags"] if f.check == "duplicate")
		self.assertEqual([o.name for o in dup.others], [b])

		review.hide_duplicate(b)
		self.assertEqual(frappe.db.get_value("RD Item", b, "published"), 0)
		self.assertNotIn("duplicate", self._flags(b))

	def test_editing_the_book_answers_its_questions(self):
		from sok_resdesk import review

		item = _item(4)
		frappe.db.set_value("RD Item", item, {"year": 0, "published": 1})
		review.scan([item])
		self.assertIn("no_year", self._flags(item))
		doc = frappe.get_doc("RD Item", item)
		doc.year = 1948
		doc.save()  # the book's form: on_update checks it again
		self.assertNotIn("no_year", self._flags(item))
