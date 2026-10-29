"""Integration tests for budgets and invoices, periodicals, interlibrary loan and online payment of fines.
Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_lending_more
"""

import hashlib
import hmac
import json
from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from sok_resdesk import acquisitions, ill, lending, payments, serials
from sok_resdesk.catalogue import upsert_item
from sok_resdesk.core import payments as pay_rules

CAT = "rdtest-more"
EMAIL = "rd-more-test@example.org"
ITEM = "rdtest-more-1"
TABLES = (
	"RD Fine Payment",
	"RD ILL Request",
	"RD Serial Issue",
	"RD Serial Subscription",
	"RD Invoice",
	"RD Fine",
	"RD Hold",
	"RD Loan",
	"RD Copy",
	"RD Patron",
	"RD Purchase Order",
	"RD Budget",
	"RD Vendor",
)


def patron(name, **values):
	doc = frappe.get_doc(
		{"doctype": "RD Patron", "full_name": name, "category": CAT, "status": "Active", **values}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestMoreLending(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		s = frappe.get_single("RD Settings")
		cls.saved = (s.feature_lending, s.payment_provider, s.lending_ill_max)

	def setUp(self):
		frappe.set_user("Administrator")
		self.settings(feature_lending=1, payment_provider="Off", lending_ill_max=3)
		self.clean()
		if not frappe.db.exists("RD Patron Category", CAT):
			frappe.get_doc(
				{
					"doctype": "RD Patron Category",
					"category_name": CAT,
					"loan_days": 7,
					"max_loans": 5,
					"fine_per_day": 2,
				}
			).insert(ignore_permissions=True)
		upsert_item({"item_id": ITEM, "source": "Other", "title": "A Book", "creators": ["Test"]})
		frappe.get_doc({"doctype": "RD Vendor", "vendor_name": "Test Vendor"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		self.clean()
		s = frappe.get_single("RD Settings")
		s.feature_lending, s.payment_provider, s.lending_ill_max = self.saved
		s.razorpay_key_id = s.razorpay_key_secret = s.razorpay_webhook_secret = ""
		s.save(ignore_permissions=True)
		frappe.db.commit()

	def settings(self, **values):
		s = frappe.get_single("RD Settings")
		for key, value in values.items():
			s.set(key, value)
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="RD Settings")

	def clean(self):
		for dt in TABLES:
			frappe.db.delete(dt)
		if frappe.db.exists("User", EMAIL):
			frappe.delete_doc("User", EMAIL, force=True, ignore_permissions=True)
		frappe.db.delete("RD Item", {"name": ("like", "rdtest-more%")})
		frappe.db.delete("RD Item", {"name": ("like", "acq-%")})
		frappe.db.delete("RD Item", {"name": ("like", "ser-%")})

	def order(self, qty, price, **values):
		return frappe.get_doc(
			{
				"doctype": "RD Purchase Order",
				"vendor": "Test Vendor",
				"lines": [{"title": "Ordered Title", "quantity": qty, "unit_price": price}],
				**values,
			}
		).insert(ignore_permissions=True)

	def invoice(self, order, number, amount):
		return frappe.get_doc(
			{
				"doctype": "RD Invoice",
				"vendor": "Test Vendor",
				"order": order,
				"invoice_number": number,
				"invoice_date": nowdate(),
				"amount": amount,
			}
		).insert(ignore_permissions=True)

	# -- budgets and invoices --------------------------------------------------------------------

	def test_a_budget_refuses_an_order_that_does_not_fit(self):
		frappe.get_doc({"doctype": "RD Budget", "budget_name": "Test Budget", "amount": 250}).insert(
			ignore_permissions=True
		)
		too_big = self.order(3, 100, budget="Test Budget")
		with self.assertRaises(frappe.ValidationError):
			acquisitions.place(too_big.name)
		fits = self.order(2, 100, budget="Test Budget")
		acquisitions.place(fits.name)
		s = acquisitions.budget_summary("Test Budget")
		self.assertEqual((s["committed"], s["spent"], s["remaining"]), (200, 0, 50))

	def test_an_invoice_turns_a_commitment_into_spending_and_is_checked(self):
		frappe.get_doc({"doctype": "RD Budget", "budget_name": "Test Budget", "amount": 1000}).insert(
			ignore_permissions=True
		)
		po = self.order(2, 100, budget="Test Budget")
		acquisitions.place(po.name)
		acquisitions.receive(po.name)
		inv = self.invoice(po.name, "A-1", 200)
		self.assertEqual(inv.match, "ok")
		self.assertEqual(inv.budget, "Test Budget")  # taken from the order
		with self.assertRaises(frappe.ValidationError):
			self.invoice(po.name, "A-1", 200)  # the same number twice
		acquisitions.invoice_approve(inv.name)
		acquisitions.invoice_pay(inv.name, "cheque 12")
		self.assertEqual(frappe.db.get_value("RD Invoice", inv.name, "status"), "Paid")
		s = acquisitions.budget_summary("Test Budget")
		self.assertEqual((s["committed"], s["spent"], s["remaining"]), (0, 200, 800))
		over = self.invoice(po.name, "A-2", 400)
		self.assertEqual(over.match, "over order")

	def test_an_invoice_for_books_that_have_not_come_is_flagged(self):
		po = self.order(2, 100)
		acquisitions.place(po.name)
		self.assertEqual(self.invoice(po.name, "B-1", 200).match, "over received")

	def test_an_approved_invoice_cannot_be_edited_or_forced_into_a_state(self):
		po = self.order(1, 100)
		forced = frappe.get_doc(
			{
				"doctype": "RD Invoice",
				"vendor": "Test Vendor",
				"order": po.name,
				"invoice_number": "d-1",
				"invoice_date": nowdate(),
				"amount": 100,
				"status": "Paid",
				"approved_by": "Administrator",
			}
		).insert(ignore_permissions=True)
		self.assertEqual((forced.status, forced.approved_by, forced.invoice_number), ("Draft", None, "D-1"))
		with self.assertRaises(frappe.ValidationError):
			self.invoice(po.name, " d-1 ", 100)  # the same number in other letters
		forced.status = "Paid"
		with self.assertRaises(frappe.ValidationError):
			forced.save(ignore_permissions=True)  # only the buttons change the state
		acquisitions.invoice_approve(forced.name)
		doc = frappe.get_doc("RD Invoice", forced.name)
		doc.amount = 100000
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)  # approved: cancel and enter another
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("RD Invoice", forced.name, ignore_permissions=True)

	def test_the_manager_who_entered_an_invoice_can_be_kept_from_approving_it(self):
		self.settings(invoice_separate_approval=1)
		inv = self.invoice(self.order(1, 100).name, "E-1", 100)
		with self.assertRaises(frappe.ValidationError):
			acquisitions.invoice_approve(inv.name)  # entered by this user
		self.settings(invoice_separate_approval=0)
		acquisitions.invoice_approve(inv.name)

	def test_money_decisions_are_for_managers(self):
		po = self.order(1, 100)
		inv = self.invoice(po.name, "C-1", 100)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			acquisitions.invoice_approve(inv.name)

	# -- periodicals -----------------------------------------------------------------------------

	def subscription(self, **values):
		return frappe.get_doc(
			{
				"doctype": "RD Serial Subscription",
				"title": "The Monthly",
				"frequency": "Monthly",
				"first_issue_due": "2026-01-31",
				"claim_after_days": 14,
				**values,
			}
		).insert(ignore_permissions=True)

	def test_issues_are_generated_checked_in_as_reference_copies_and_continue(self):
		sub = self.subscription()
		self.assertEqual(serials.generate(sub.name, 3)["made"], 3)
		issues = frappe.get_all(
			"RD Serial Issue",
			filters={"subscription": sub.name},
			fields=["name", "expected_on", "label"],
			order_by="expected_on asc",
		)
		self.assertEqual([str(i.expected_on) for i in issues], ["2026-01-31", "2026-02-28", "2026-03-31"])
		self.assertEqual(issues[1].label, "February 2026")
		out = serials.receive(issues[0].name)
		self.assertTrue(out["barcode"])
		copy = frappe.get_doc("RD Copy", out["barcode"])
		self.assertEqual(copy.reference_only, 1)
		self.assertTrue(
			frappe.db.get_value("RD Serial Subscription", sub.name, "item")
		)  # the periodical's record
		with self.assertRaises(frappe.ValidationError):
			serials.receive(issues[0].name)  # twice
		serials.generate(sub.name, 2)  # continues after the last
		self.assertEqual(frappe.db.count("RD Serial Issue", {"subscription": sub.name}), 5)

	def test_an_overdue_issue_becomes_late_and_can_be_claimed(self):
		sub = self.subscription()
		serials.generate(sub.name, 1)
		name = frappe.get_all("RD Serial Issue", filters={"subscription": sub.name}, pluck="name")[0]
		frappe.db.set_value("RD Serial Issue", name, "expected_on", getdate(nowdate()) - timedelta(days=30))
		serials.daily()
		self.assertEqual(frappe.db.get_value("RD Serial Issue", name, "status"), "Late")
		serials.claim(name)
		self.assertEqual(frappe.db.get_value("RD Serial Issue", name, "status"), "Claimed")

	# -- interlibrary loan -----------------------------------------------------------------------

	def test_borrowing_follows_its_steps_and_a_fee_becomes_a_fine(self):
		a = patron("Asha")
		req = frappe.get_doc(
			{
				"doctype": "RD ILL Request",
				"direction": "Borrowing",
				"patron": a,
				"title": "A Rare Book",
				"fee": 50,
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			ill.advance(req.name, "Sent")  # to whom?
		frappe.db.set_value("RD ILL Request", req.name, "partner_library", "State Library")
		ill.advance(req.name, "Sent")
		with self.assertRaises(frappe.ValidationError):
			ill.advance(req.name, "Lent to Patron")  # it has not arrived
		ill.advance(req.name, "Received")
		ill.advance(req.name, "Lent to Patron")
		self.assertTrue(frappe.db.get_value("RD ILL Request", req.name, "due_on"))
		ill.charge_fee(req.name)
		self.assertEqual(lending.fines_due(a), 50)
		with self.assertRaises(frappe.ValidationError):
			ill.charge_fee(req.name)  # once
		for step in ("Returned", "Sent Back", "Closed"):
			ill.advance(req.name, step)
		self.assertEqual(frappe.db.get_value("RD ILL Request", req.name, "status"), "Closed")

	def test_lending_a_copy_to_another_library_takes_it_off_the_shelf_until_it_returns(self):
		copy = (
			frappe.get_doc({"doctype": "RD Copy", "item": ITEM, "barcode": "RDTEST-M1"})
			.insert(ignore_permissions=True)
			.name
		)
		b = patron("Bala")
		req = frappe.get_doc(
			{
				"doctype": "RD ILL Request",
				"direction": "Lending",
				"partner_library": "College Library",
				"title": "A Book",
				"copy": copy,
			}
		).insert(ignore_permissions=True)
		ill.advance(req.name, "Approved")
		ill.advance(req.name, "Sent")
		self.assertEqual(frappe.db.get_value("RD Copy", copy, "status"), "Interlibrary loan")
		with self.assertRaises(frappe.ValidationError):
			lending.checkout(b, copy)
		ill.advance(req.name, "Returned")
		self.assertEqual(frappe.db.get_value("RD Copy", copy, "status"), "Available")

	def test_a_member_asks_for_a_book_within_the_limit_and_cancels_before_it_starts(self):
		a = patron("Asha")
		user = frappe.get_doc(
			{"doctype": "User", "email": EMAIL, "first_name": "Asha", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		frappe.db.set_value("RD Patron", a, "user", user.name)
		self.settings(lending_ill_max=1)
		frappe.set_user(EMAIL)
		out = ill.request_mine("A Rare Book", author="Someone")
		self.assertEqual(frappe.db.get_value("RD ILL Request", out["request"], "status"), "Requested")
		with self.assertRaises(frappe.ValidationError):
			ill.request_mine("Another")  # one open at a time
		with self.assertRaises(frappe.ValidationError):
			ill.request_mine("   ")
		ill.cancel_mine(out["request"])
		self.assertEqual(frappe.db.get_value("RD ILL Request", out["request"], "status"), "Cancelled")
		frappe.set_user("Administrator")
		other = frappe.get_doc(
			{"doctype": "RD ILL Request", "direction": "Borrowing", "patron": patron("Bala"), "title": "X"}
		).insert(ignore_permissions=True)
		frappe.set_user(EMAIL)
		with self.assertRaises(frappe.PermissionError):
			ill.cancel_mine(other.name)

	# -- online payment of fines -----------------------------------------------------------------

	def fine_payment(self, member, amount):
		fine = frappe.get_doc(
			{"doctype": "RD Fine", "patron": member, "reason": "Overdue", "amount": amount, "status": "Due"}
		).insert(ignore_permissions=True)
		pay = frappe.get_doc(
			{
				"doctype": "RD Fine Payment",
				"patron": member,
				"amount": amount,
				"status": "Created",
				"provider": "Razorpay",
				"provider_ref": "plink_1",
				"fine_names": fine.name,
			}
		).insert(ignore_permissions=True)
		return fine.name, pay.name

	def event(self, ref, paise, status="paid"):
		return json.dumps(
			{
				"event": "payment_link.paid",
				"payload": {
					"payment_link": {
						"entity": {
							"id": "plink_1",
							"reference_id": ref,
							"amount": paise,
							"amount_paid": paise,
							"status": status,
						}
					},
					"payment": {"entity": {"id": "pay_test1"}},
				},
			}
		).encode()

	def hook(self):
		self.settings(
			payment_provider="Razorpay",
			razorpay_key_id="rzp_test_x",
			razorpay_key_secret="secret",
			razorpay_webhook_secret="hook-secret",
		)

	def sign(self, body):
		return hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()

	def test_online_payment_is_off_until_it_is_set_up(self):
		self.assertFalse(payments.configured())
		self.hook()
		self.assertTrue(payments.configured())

	def test_a_signed_paid_event_marks_the_fines_paid_once(self):
		self.hook()
		a = patron("Asha")
		fine, pay = self.fine_payment(a, 25)
		body = self.event(pay, pay_rules.to_paise(25))
		payments.process_webhook(body, self.sign(body))
		self.assertEqual(frappe.db.get_value("RD Fine", fine, "status"), "Paid")
		self.assertEqual(frappe.db.get_value("RD Fine Payment", pay, "status"), "Paid")
		self.assertEqual(payments.process_webhook(body, self.sign(body)), {"ok": 1})  # told twice

	def test_a_wrong_signature_or_amount_changes_nothing(self):
		self.hook()
		a = patron("Asha")
		fine, pay = self.fine_payment(a, 25)
		body = self.event(pay, 2500)
		with self.assertRaises(frappe.DoesNotExistError):  # the same answer as "not set up"
			payments.process_webhook(body, "0" * 64)
		short = self.event(pay, 100)  # signed, but not what was asked
		self.assertEqual(payments.process_webhook(short, self.sign(short)).get("mismatch"), 1)
		self.assertEqual(frappe.db.get_value("RD Fine", fine, "status"), "Due")

	def test_a_link_this_site_did_not_make_is_ignored(self):
		self.hook()
		a = patron("Asha")
		fine, pay = self.fine_payment(a, 25)
		body = self.event(pay, 2500).replace(b"plink_1", b"plink_other")
		self.assertEqual(payments.process_webhook(body, self.sign(body)).get("ignored"), 1)
		self.assertEqual(frappe.db.get_value("RD Fine", fine, "status"), "Due")

	def test_money_for_a_fine_the_desk_already_cleared_is_logged_for_a_refund(self):
		self.hook()
		a = patron("Asha")
		fine, pay = self.fine_payment(a, 25)
		frappe.db.set_value("RD Fine", fine, "status", "Paid")  # cash at the desk meanwhile
		before = frappe.db.count("Error Log")
		body = self.event(pay, 2500)
		payments.process_webhook(body, self.sign(body))
		self.assertEqual(frappe.db.get_value("RD Fine Payment", pay, "status"), "Paid")
		self.assertGreater(frappe.db.count("Error Log"), before)

	def test_the_webhook_does_not_exist_while_online_payment_is_off(self):
		body = self.event("FP-00001", 100)
		with self.assertRaises(frappe.DoesNotExistError):
			payments.process_webhook(body, self.sign(body))
