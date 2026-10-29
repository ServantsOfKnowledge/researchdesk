"""The rules of lending (core/lending.py)."""

from datetime import date

from sok_resdesk.core import lending as L

MON = date(2026, 11, 2)  # a Monday


def ok(**kw):
	base = dict(
		status="Active", valid_until=None, today=MON, loans_out=0, max_loans=3, fines_due=0, block_fines_over=0,
		copy_status="Available",
	)  # fmt: skip
	return L.borrow_check(**{**base, **kw})


def test_closed_days_are_read_from_words():
	assert L.closed_days("Sunday, saturday") == {5, 6}
	assert L.closed_days("Funday") == set() and L.closed_days("") == set()


def test_a_due_date_skips_the_days_the_library_is_closed():
	assert L.due_date(MON, 14) == date(2026, 11, 16)
	assert L.due_date(MON, 13, {6}) == date(2026, 11, 16)  # the 15th is a Sunday
	assert L.due_date(MON, 0) == date(2026, 11, 3)  # at least a day
	assert L.due_date(MON, 7, set(range(7))) == date(2026, 11, 9)  # closed always: no endless loop


def test_fines_count_days_after_grace_and_stop_at_the_cap():
	due = date(2026, 11, 10)
	assert L.fine(due, date(2026, 11, 10), 2) == 0
	assert L.fine(due, date(2026, 11, 15), 2) == 10
	assert L.fine(due, date(2026, 11, 15), 2, grace=2) == 6
	assert L.fine(due, date(2026, 12, 25), 2, cap=50) == 50
	assert L.fine(due, date(2026, 11, 15), 0) == 0


def test_a_membership_ends_the_day_before_its_anniversary():
	assert L.membership_end(date(2026, 6, 15), 12) == date(2027, 6, 14)
	assert L.membership_end(date(2026, 1, 31), 1) == date(2026, 2, 27)
	assert L.membership_end(date(2026, 6, 15), 0) is None


def test_who_may_borrow():
	assert ok() is None
	assert ok(status="Blocked") == "blocked"
	assert ok(status="Pending") == "not_active"
	assert ok(valid_until=date(2026, 10, 31)) == "expired"
	assert ok(loans_out=3) == "loan_limit"
	assert ok(block_fines_over=50, fines_due=60) == "fines"
	assert ok(copy_status="On loan") == "on_loan"
	assert ok(copy_status="Lost") == "copy_gone"
	assert ok(reference_only=True) == "reference"
	assert ok(copy_status="On hold shelf", held_for="M-2", patron="M-1") == "held_for_other"
	assert ok(copy_status="On hold shelf", held_for="M-1", patron="M-1") is None


def test_renewals():
	kw = dict(renewals=0, max_renewals=2, overdue=False, waiting_holds=0)
	assert L.renew_check(**kw) is None
	assert L.renew_check(**{**kw, "renewals": 2}) == "renew_limit"
	assert L.renew_check(**{**kw, "overdue": True}) == "renew_overdue"
	assert L.renew_check(**{**kw, "overdue": True, "allow_overdue": True}) is None
	assert L.renew_check(**{**kw, "waiting_holds": 1}) == "renew_held"
	assert L.renew_check(**{**kw, "standing": "blocked"}) == "blocked"


def test_holds_are_for_books_that_are_out():
	kw = dict(standing=None, holds=0, max_holds=2, already_has=False, copies_total=2, copies_available=0)
	assert L.hold_check(**kw) is None
	assert L.hold_check(**{**kw, "copies_available": 1}) == "hold_available"
	assert L.hold_check(**{**kw, "copies_total": 0}) == "hold_none"
	assert L.hold_check(**{**kw, "holds": 2}) == "hold_limit"
	assert L.hold_check(**{**kw, "already_has": True}) == "hold_have"


def test_id_numbers_compare_without_punctuation():
	assert L.normal_id(" cs-21/045 ") == "CS21045"


def test_only_the_date_of_birth_makes_a_member_an_email_waits_for_staff():
	roster = {"email": "Asha@Example.org", "date_of_birth": date(2008, 5, 4)}
	assert L.match_level(roster, date(2008, 5, 4), "") == "strong"
	assert L.match_level(roster, date(2008, 5, 4), "other@example.org") == "strong"
	assert L.match_level(roster, None, "asha@example.org") == "weak"  # anyone can type an email
	assert L.match_level(roster, date(2008, 5, 5), "other@example.org") == ""
	assert L.match_level(roster, None, "") == ""
	assert L.match_level({"email": "", "date_of_birth": None}, None, "") == ""
