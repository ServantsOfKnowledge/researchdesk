"""Budgets, serials, interlibrary loan and online payments (core/budget.py, serials.py, ill.py, payments.py)."""

import hashlib
import hmac
import json
from datetime import date

from sok_resdesk.core import budget, ill, payments, serials


def test_an_order_holds_back_what_is_not_yet_invoiced():
	assert budget.commitment(1000, "Draft", 0) == 0
	assert budget.commitment(1000, "Ordered", 0) == 1000
	assert budget.commitment(1000, "Part Received", 400) == 600
	assert budget.commitment(1000, "Received", 1200) == 0  # invoiced over the order: nothing left to hold
	assert budget.commitment(1000, "Cancelled", 0) == 0


def test_the_budget_summary_adds_committed_and_spent():
	s = budget.summary(5000, [(1000, "Ordered", 0), (800, "Received", 800), (300, "Draft", 0)], 800 + 200)
	assert s == {"amount": 5000, "committed": 1000, "spent": 1000, "used": 2000, "remaining": 3000}
	assert budget.fits(5000, [(1000, "Ordered", 0)], 0, 4000)
	assert not budget.fits(5000, [(1000, "Ordered", 0)], 0, 4000.5)


def test_an_invoice_is_checked_against_the_order_and_what_arrived():
	assert budget.three_way(100, 100, 100) == "ok"
	assert budget.three_way(104, 100, 100) == "ok"  # within 5%
	assert budget.three_way(100, 100, 60) == "over received"  # asks for more than came
	assert budget.three_way(120, 100, 100) == "over order"
	assert budget.received_value([(2, 50), (1, 25.5)]) == 125.5


def test_issues_keep_their_day_and_months_are_clamped():
	assert serials.expected_dates(date(2026, 1, 31), "Monthly", 3) == [
		date(2026, 1, 31),
		date(2026, 2, 28),
		date(2026, 3, 31),
	]
	assert serials.expected_dates(date(2026, 1, 5), "Weekly", 3) == [
		date(2026, 1, 5),
		date(2026, 1, 12),
		date(2026, 1, 19),
	]
	assert serials.expected_dates(date(2026, 1, 15), "Quarterly", 2)[1] == date(2026, 4, 15)
	assert serials.expected_dates(date(2026, 1, 15), "Yearly", 0) == []
	assert serials.label(date(2026, 3, 15), "Monthly") == "March 2026"
	assert serials.label(date(2026, 3, 15), "Weekly") == "15 Mar 2026"


def test_an_issue_is_late_after_the_claim_period():
	assert not serials.is_late(date(2026, 3, 1), date(2026, 3, 15), 14)
	assert serials.is_late(date(2026, 3, 1), date(2026, 3, 16), 14)


def test_interlibrary_loan_follows_its_steps():
	assert ill.allowed("Borrowing", "Requested") == ("Sent", "Refused", "Cancelled")
	assert ill.can_move("Borrowing", "Received", "Lent to Patron")
	assert not ill.can_move("Borrowing", "Received", "Closed")  # a received book must reach the member first
	assert not ill.can_move("Borrowing", "Lent to Patron", "Cancelled")
	assert ill.can_move("Lending", "Approved", "Sent")
	assert ill.allowed("Lending", "Closed") == ()
	assert not ill.is_open("Refused") and ill.is_open("Sent")


def test_money_is_in_whole_paise_and_the_link_sends_no_message():
	assert payments.to_paise(12.5) == 1250
	assert payments.to_paise("10.005") == 1001  # half up, no float surprise
	assert payments.to_paise(0.1 + 0.2) == 30
	body = payments.link_payload(25, "FP-00001", "Library fines", "Asha", "https://lib.example/library/loans")
	assert body["amount"] == 2500 and body["reference_id"] == "FP-00001"
	assert body["notify"] == {"sms": False, "email": False} and body["accept_partial"] is False


def test_only_a_correctly_signed_webhook_is_believed():
	raw = b'{"event":"payment_link.paid"}'
	good = hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
	assert payments.valid_signature(raw, good, "s3cret")
	assert not payments.valid_signature(raw, good, "other")
	assert not payments.valid_signature(raw + b" ", good, "s3cret")
	assert not payments.valid_signature(raw, "", "s3cret") and not payments.valid_signature(raw, good, "")
	assert not payments.valid_signature(raw, "é" * 64, "s3cret")  # any header text: false, not an error


def test_a_paid_event_is_read_and_anything_else_is_ignored():
	event = {
		"event": "payment_link.paid",
		"payload": {
			"payment_link": {
				"entity": {
					"id": "plink_1",
					"reference_id": "FP-00001",
					"amount": 2500,
					"amount_paid": 2500,
					"status": "paid",
				}
			},
			"payment": {"entity": {"id": "pay_abc"}},
		},
	}
	assert payments.paid_event(event) == ("FP-00001", 2500, "pay_abc", "plink_1")
	assert payments.paid_event({**event, "event": "payment_link.cancelled"}) is None
	event["payload"]["payment_link"]["entity"]["status"] = "partially_paid"
	assert payments.paid_event(event) is None
	event["payload"]["payment_link"]["entity"]["status"] = "paid"
	event["payload"]["payment_link"]["entity"]["currency"] = "USD"
	assert payments.paid_event(event) is None  # only rupees
	assert payments.paid_event({"event": "payment_link.paid", "payload": {}}) is None
	assert payments.paid_event(json.loads("[]")) is None


def test_every_doctype_has_its_python_module():
	"""A doctype folder without its .py file fails the site install (0.106.0)."""
	import pathlib

	root = pathlib.Path(__file__).resolve().parents[1] / "resdesk" / "doctype"
	for folder in root.iterdir():
		if (folder / f"{folder.name}.json").exists():
			assert (folder / f"{folder.name}.py").exists(), folder.name
