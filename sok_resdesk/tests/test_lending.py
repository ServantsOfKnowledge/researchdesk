"""Integration tests for members, lending and acquisitions. Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_lending
"""

from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from sok_resdesk import access, acquisitions, lending, patrons
from sok_resdesk.catalogue import upsert_item

CAT = "rdtest-student"
EMAIL = "rd-member-test@example.org"
ITEM = "rdtest-lend-1"


def patron(name, **values):
	doc = frappe.get_doc(
		{"doctype": "RD Patron", "full_name": name, "category": CAT, "status": "Active", **values}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestLending(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		s = frappe.get_single("RD Settings")
		cls.saved = (s.feature_lending, s.lending_default_category, s.lending_closed_days)

	def setUp(self):
		frappe.set_user("Administrator")
		self.settings(feature_lending=1, lending_closed_days="", lending_default_category=None)
		self.clean()
		if not frappe.db.exists("RD Patron Category", CAT):
			frappe.get_doc(
				{
					"doctype": "RD Patron Category",
					"category_name": CAT,
					"loan_days": 7,
					"max_loans": 2,
					"max_renewals": 1,
					"max_holds": 3,
					"fine_per_day": 2,
					"validity_months": 12,
				}
			).insert(ignore_permissions=True)
		upsert_item({"item_id": ITEM, "source": "Other", "title": "A Book for Lending", "creators": ["Test"]})
		self.copy = self.make_copy("RDTEST-C1")

	def tearDown(self):
		frappe.set_user("Administrator")
		self.clean()
		s = frappe.get_single("RD Settings")
		s.feature_lending, s.lending_default_category, s.lending_closed_days = self.saved
		s.save(ignore_permissions=True)
		frappe.db.commit()

	def settings(self, **values):
		s = frappe.get_single("RD Settings")
		for key, value in values.items():
			s.set(key, value)
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")

	def clean(self):
		for dt in ("RD Fine", "RD Hold", "RD Loan", "RD Copy", "RD Patron", "RD Purchase Order", "RD Vendor"):
			frappe.db.delete(dt)
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		frappe.db.delete("RD Item", {"name": ("like", "rdtest-lend%")})
		frappe.db.delete("RD Item", {"name": ("like", "acq-%")})

	def make_copy(self, barcode, **values):
		doc = frappe.get_doc({"doctype": "RD Copy", "item": ITEM, "barcode": barcode, **values})
		doc.insert(ignore_permissions=True)
		return doc.name

	def status(self, copy):
		return frappe.db.get_value("RD Copy", copy, "status")

	def test_lend_and_return(self):
		a, b = patron("Asha"), patron("Bala")
		out = lending.checkout(a, "rdtest-c1")  # a scanner or a typist: case does not matter
		self.assertEqual(self.status(self.copy), "On loan")
		self.assertEqual(out["due_on"], str(add_days(getdate(nowdate()), 7)))
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(b, self.copy)  # already out
		back = lending.checkin(self.copy)
		self.assertEqual(back["fine"], 0)
		self.assertEqual(self.status(self.copy), "Available")
		self.assertEqual(frappe.db.get_value("RD Loan", out["loan"], "status"), "Returned")

	def test_a_late_return_is_fined_by_the_category(self):
		a = patron("Asha")
		out = lending.checkout(a, self.copy)
		frappe.db.set_value("RD Loan", out["loan"], "due_on", getdate(nowdate()) - timedelta(days=5))
		back = lending.checkin(self.copy)
		self.assertEqual(back["fine"], 10)
		self.assertEqual(lending.fines_due(a), 10)
		fine = frappe.get_all("RD Fine", filters={"patron": a}, pluck="name")[0]
		lending.settle_fine(fine)
		self.assertEqual(lending.fines_due(a), 0)

	def test_the_loan_limit_and_an_expired_member_are_refused(self):
		a = patron("Asha")
		self.make_copy("RDTEST-C2")
		self.make_copy("RDTEST-C3")
		lending.checkout(a, "RDTEST-C1")
		lending.checkout(a, "RDTEST-C2")
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(a, "RDTEST-C3")  # two at once
		old = patron("Old", valid_until=getdate(nowdate()) - timedelta(days=3))
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(old, "RDTEST-C3")

	def test_a_hold_keeps_the_returned_copy_for_the_member_waiting(self):
		a, b = patron("Asha"), patron("Bala")
		lending.checkout(a, self.copy)
		lending.place_hold_for(b, ITEM)
		with self.assertRaises(frappe.ValidationError):
			lending.place_hold_for(b, ITEM)  # already waiting
		back = lending.checkin(self.copy)
		self.assertEqual(back["hold_for"], "Bala")
		self.assertEqual(self.status(self.copy), "On hold shelf")
		c = patron("Chitra")
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(c, self.copy)  # kept for Bala
		lending.checkout(b, self.copy)
		self.assertEqual(frappe.db.get_value("RD Hold", {"patron": b}, "status"), "Fulfilled")

	def test_a_loan_cannot_be_renewed_while_someone_waits(self):
		a, b = patron("Asha"), patron("Bala")
		out = lending.checkout(a, self.copy)
		lending.renew(out["loan"])  # nobody waiting: fine
		with self.assertRaises(frappe.ValidationError):
			lending.renew(out["loan"])  # one renewal only
		self.make_copy("RDTEST-C2")  # a hold needs every copy out
		lending.checkout(b, "RDTEST-C2")
		c = patron("Chitra")
		lending.place_hold_for(c, ITEM)
		with self.assertRaises(frappe.ValidationError):
			lending.renew(frappe.db.get_value("RD Loan", {"patron": b, "status": "Out"}, "name"))

	def test_a_hold_is_for_a_book_that_is_out(self):
		b = patron("Bala")
		with self.assertRaises(frappe.ValidationError):
			lending.place_hold_for(b, ITEM)  # a copy is on the shelf

	def test_a_member_cannot_hold_a_book_they_may_not_see(self):
		a = patron("Asha")
		user = frappe.get_doc(
			{"doctype": "User", "email": EMAIL, "first_name": "Asha", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.db.set_value("RD Patron", a, "user", user.name)
		b = patron("Bala")
		lending.checkout(b, self.copy)  # every copy out
		frappe.db.set_value("RD Item", ITEM, "published", 0)
		frappe.set_user(EMAIL)
		with self.assertRaises(frappe.ValidationError):
			lending.my_hold(ITEM)

	def test_a_lost_book_charges_its_price(self):
		a = patron("Asha")
		frappe.db.set_value("RD Copy", self.copy, "price", 250)
		out = lending.checkout(a, self.copy)
		lending.mark_lost(out["loan"])
		self.assertEqual(self.status(self.copy), "Lost")
		self.assertEqual(lending.fines_due(a), 250)

	def test_nothing_works_while_the_feature_is_off(self):
		a = patron("Asha")
		self.settings(feature_lending=0)
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(a, self.copy)

	def test_a_member_sees_and_holds_only_their_own(self):
		a = patron("Asha")
		user = frappe.get_doc(
			{"doctype": "User", "email": EMAIL, "first_name": "Asha", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.db.set_value("RD Patron", a, "user", user.name)
		lending.checkout(a, self.copy)
		frappe.set_user(EMAIL)
		self.assertEqual(lending.my()["patron"]["name"], a)
		self.assertEqual(len(lending.my()["loans"]), 1)
		frappe.set_user("Administrator")
		b = patron("Bala")
		out = lending.checkout(b, self.make_copy("RDTEST-C2"))
		frappe.set_user(EMAIL)
		with self.assertRaises(frappe.PermissionError):
			lending.my_renew(out["loan"])  # not theirs

	def test_old_returned_loans_are_forgotten_but_unpaid_fines_keep_theirs(self):
		a = patron("Asha")
		self.settings(lending_keep_days=30)
		self.addCleanup(self.settings, lending_keep_days=180)
		out = lending.checkout(a, self.copy)
		lending.checkin(self.copy)
		frappe.db.set_value("RD Loan", out["loan"], "returned_on", getdate(nowdate()) - timedelta(days=90))
		lending.daily()
		self.assertFalse(frappe.db.exists("RD Loan", out["loan"]))

	def test_receiving_an_order_makes_copies_with_barcodes(self):
		frappe.get_doc({"doctype": "RD Vendor", "vendor_name": "Test Books"}).insert(ignore_permissions=True)
		po = frappe.get_doc(
			{
				"doctype": "RD Purchase Order",
				"vendor": "Test Books",
				"lines": [{"title": "Brand New Title", "author": "Writer", "quantity": 3, "unit_price": 100}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(po.total, 300)
		with self.assertRaises(frappe.ValidationError):
			acquisitions.receive(po.name)  # not placed yet
		acquisitions.place(po.name)
		out = acquisitions.receive(po.name, {"1": 2})
		self.assertEqual(len(out["copies"]), 2)
		self.assertEqual(out["status"], "Part Received")
		out = acquisitions.receive(po.name)
		self.assertEqual(len(out["copies"]), 1)
		self.assertEqual(out["status"], "Received")
		item = frappe.get_doc("RD Order Line", {"parent": po.name}).item
		self.assertTrue(item)
		self.assertEqual(frappe.db.count("RD Copy", {"item": item, "order": po.name}), 3)
		self.assertEqual(frappe.db.get_value("RD Copy", {"order": po.name}, "price"), 100)


class TestJoinWithAnIdCard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		s = frappe.get_single("RD Settings")
		cls.saved = (s.feature_lending, s.lending_default_category)

	def setUp(self):
		frappe.set_user("Administrator")
		s = frappe.get_single("RD Settings")
		s.feature_lending = 1
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")
		for dt in ("RD Patron",):
			frappe.db.delete(dt)
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		if not frappe.db.exists("RD Patron Category", CAT):
			frappe.get_doc({"doctype": "RD Patron Category", "category_name": CAT}).insert(
				ignore_permissions=True
			)
		s = frappe.get_single("RD Settings")
		s.lending_default_category = CAT
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")
		self.roster = patron(
			"Asha K",
			status="Listed",
			institution_id="CS-21/045",
			email="asha@school.example",
			date_of_birth="2008-05-04",
		)
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Patron")
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		s = frappe.get_single("RD Settings")
		s.feature_lending, s.lending_default_category = self.saved
		s.save(ignore_permissions=True)
		frappe.db.commit()

	def apply(self, **values):
		args = {"full_name": "Asha K", "email": EMAIL, "password": "longenough1", "id_number": "cs21045"}
		return patrons.apply(**{**args, **values})

	def test_a_person_on_the_roster_with_the_right_date_is_a_member_at_once(self):
		out = self.apply(date_of_birth="2008-05-04")
		self.assertEqual(out["status"], "joined")  # the same word as for anyone: My library says more
		self.assertIn(access.READER_ROLE, [r.role for r in frappe.get_doc("User", EMAIL).roles])
		row = frappe.db.get_value(
			"RD Patron", self.roster, ["status", "user", "valid_until", "date_of_birth"], as_dict=True
		)
		self.assertEqual((row.status, row.user), ("Active", EMAIL))
		self.assertTrue(row.valid_until)
		self.assertFalse(row.date_of_birth)  # forgotten once it has done its job

	def test_the_registered_email_alone_never_makes_a_member(self):
		out = self.apply(email="asha@school.example")  # anyone can type it
		self.assertEqual(out["status"], "joined")
		self.assertNotIn(
			access.READER_ROLE, [r.role for r in frappe.get_doc("User", "asha@school.example").roles]
		)
		row = frappe.db.get_value("RD Patron", self.roster, ["status", "user"], as_dict=True)
		self.assertEqual((row.status, row.user), ("Pending", "asha@school.example"))
		frappe.set_user("Administrator")
		frappe.delete_doc("User", "asha@school.example", force=True, ignore_permissions=True)

	def test_a_wrong_date_waits_for_a_manager_and_is_not_a_reader(self):
		self.apply(date_of_birth="2001-01-01")
		self.assertNotIn(access.READER_ROLE, [r.role for r in frappe.get_doc("User", EMAIL).roles])
		pending = frappe.get_all("RD Patron", filters={"user": EMAIL}, fields=["name", "status"])[0]
		self.assertEqual(pending.status, "Pending")
		self.assertEqual(frappe.db.get_value("RD Patron", self.roster, "status"), "Listed")  # untouched
		frappe.set_user("Administrator")
		patrons.approve(pending.name)
		self.assertEqual(frappe.db.get_value("RD Patron", pending.name, "status"), "Active")
		self.assertIn(access.READER_ROLE, [r.role for r in frappe.get_doc("User", EMAIL).roles])

	def test_a_turned_down_sign_up_keeps_neither_photo_nor_date_of_birth(self):
		self.apply(date_of_birth="2001-01-01")
		pending = frappe.get_all("RD Patron", filters={"user": EMAIL}, pluck="name")[0]
		frappe.set_user("Administrator")
		patrons.reject(pending)
		row = frappe.db.get_value(
			"RD Patron", pending, ["status", "date_of_birth", "id_card_photo"], as_dict=True
		)
		self.assertEqual(row.status, "Rejected")
		self.assertFalse(row.date_of_birth or row.id_card_photo)

	def test_only_a_manager_can_grant_membership(self):
		self.apply(date_of_birth="2001-01-01")
		pending = frappe.get_all("RD Patron", filters={"user": EMAIL}, pluck="name")[0]
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			patrons.approve(pending)

	def test_an_id_number_that_is_guessed_at_is_closed_for_the_hour(self):
		for _n in range(patrons.TRIES):
			patrons._wrong_guess("CS21045")
		with self.assertRaises(frappe.ValidationError):
			self.apply(date_of_birth="2008-05-04")  # even the right answer: it is closed
		frappe.cache.delete_value(patrons._guess_key("CS21045"))

	def test_a_signed_in_person_can_link_their_account_with_the_date_of_birth_only(self):
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "User",
				"email": "asha@school.example",
				"first_name": "Asha",
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		).insert(ignore_permissions=True)
		frappe.set_user("asha@school.example")
		with self.assertRaises(frappe.ValidationError):
			patrons.claim("CS21045", "")  # their email is the roster's, and that proves nothing
		with self.assertRaises(frappe.ValidationError):
			patrons.claim("CS21045", "2001-01-01")
		self.assertEqual(patrons.claim("CS21045", "2008-05-04")["status"], "member")
		frappe.set_user("Administrator")
		frappe.delete_doc("User", "asha@school.example", force=True, ignore_permissions=True)

	def test_a_roster_number_cannot_be_claimed_twice(self):
		self.apply(date_of_birth="2008-05-04")
		self.apply(email="second@example.org", full_name="Someone Else", date_of_birth="2008-05-04")
		self.assertEqual(frappe.db.get_value("RD Patron", self.roster, "user"), EMAIL)  # still the first
		frappe.set_user("Administrator")
		frappe.delete_doc("User", "second@example.org", force=True, ignore_permissions=True)

	def test_without_a_category_there_is_no_membership_yet(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Patron Category")
		s = frappe.get_single("RD Settings")
		s.lending_default_category = None
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			self.apply()
