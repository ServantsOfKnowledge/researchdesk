"""The rules of lending, as plain functions (no Frappe): due dates, fines, who may borrow, who may renew.

sok_resdesk/lending.py reads the facts from the database and asks these what to do, so each rule can be
tested without a site. A refusal is a short code (REASONS); the caller turns it into words.
"""

from __future__ import annotations

from datetime import date, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# patron statuses
ACTIVE, PENDING, EXPIRED, BLOCKED, LISTED, REJECTED = (
	"Active",
	"Pending",
	"Expired",
	"Blocked",
	"Listed",
	"Rejected",
)

REASONS = {
	"not_active": "This member is not active.",
	"blocked": "This member is blocked.",
	"expired": "This membership has expired.",
	"loan_limit": "This member has reached the limit of loans.",
	"fines": "This member owes more in fines than the library allows.",
	"copy_gone": "This copy cannot be lent (lost, withdrawn or not yet processed).",
	"on_loan": "This copy is already on loan.",
	"reference": "This copy is for reference in the library only.",
	"held_for_other": "This copy is kept on the hold shelf for another member.",
	"renew_limit": "This loan cannot be renewed again.",
	"renew_overdue": "An overdue loan cannot be renewed.",
	"renew_held": "Another member is waiting for this book.",
	"hold_limit": "This member has reached the limit of holds.",
	"hold_have": "This member already has this book, or a hold on it.",
	"hold_available": "A copy is on the shelf: borrow it instead of placing a hold.",
	"hold_none": "The library has no copy of this book to lend.",
}


def closed_days(text: str) -> set[int]:
	"""Weekday numbers (Monday 0) from a setting such as "Sunday, Saturday"."""
	names = {w: i for i, w in enumerate(WEEKDAYS)}
	return {
		names[w] for w in (t.strip().lower() for t in (text or "").replace(";", ",").split(",")) if w in names
	}


def open_on_or_after(day: date, closed: set[int]) -> date:
	"""The first day from `day` the library is open (the same day when it is). Never loops: a library
	closed all seven days is taken as open every day."""
	if len(closed) >= 7:
		return day
	while day.weekday() in closed:
		day += timedelta(days=1)
	return day


def due_date(issued: date, loan_days: int, closed: set[int] = frozenset()) -> date:
	"""The day a loan is due: `loan_days` on, moved to the next day the library is open."""
	return open_on_or_after(issued + timedelta(days=max(int(loan_days or 0), 1)), set(closed))


def days_overdue(due: date, today: date, grace: int = 0) -> int:
	return max((today - due).days - max(int(grace or 0), 0), 0)


def fine(due: date, returned: date, per_day: float, grace: int = 0, cap: float = 0) -> float:
	"""The overdue fine: days past the due date (less the grace days) times the daily rate, never more
	than the cap (0 = no cap)."""
	amount = days_overdue(due, returned, grace) * max(float(per_day or 0), 0.0)
	if cap and float(cap) > 0:
		amount = min(amount, float(cap))
	return round(amount, 2)


def membership_end(start: date, months: int) -> date | None:
	"""The last day of a membership that starts on `start` and runs `months` (0 = no end)."""
	if not months or months < 1:
		return None
	total = start.year * 12 + (start.month - 1) + months
	year, month = divmod(total, 12)
	month += 1
	# the day before the same date `months` later
	for day in (start.day, 28, 27):
		try:
			return date(year, month, day) - timedelta(days=1)
		except ValueError:
			continue
	return None


def patron_standing(status: str, valid_until: date | None, today: date) -> str | None:
	"""Why a patron cannot borrow, as a REASONS code; None when they can."""
	if status == BLOCKED:
		return "blocked"
	if status != ACTIVE and status != EXPIRED:
		return "not_active"
	if status == EXPIRED or (valid_until and valid_until < today):
		return "expired"
	return None


def borrow_check(
	*,
	status: str,
	valid_until: date | None,
	today: date,
	loans_out: int,
	max_loans: int,
	fines_due: float,
	block_fines_over: float,
	copy_status: str,
	reference_only: bool = False,
	held_for: str | None = None,
	patron: str = "",
) -> str | None:
	"""Whether this member may borrow this copy now: None, or the REASONS code that says why not."""
	why = patron_standing(status, valid_until, today)
	if why:
		return why
	if max_loans and loans_out >= max_loans:
		return "loan_limit"
	if block_fines_over and fines_due > float(block_fines_over):
		return "fines"
	if copy_status == "On loan":
		return "on_loan"
	if copy_status not in ("Available", "On hold shelf"):
		return "copy_gone"
	if reference_only:
		return "reference"
	if copy_status == "On hold shelf" and held_for and held_for != patron:
		return "held_for_other"
	return None


def renew_check(
	*,
	renewals: int,
	max_renewals: int,
	overdue: bool,
	waiting_holds: int,
	allow_overdue: bool = False,
	standing: str | None = None,
) -> str | None:
	if standing:
		return standing
	if renewals >= max_renewals:
		return "renew_limit"
	if overdue and not allow_overdue:
		return "renew_overdue"
	if waiting_holds:
		return "renew_held"
	return None


def hold_check(
	*,
	standing: str | None,
	holds: int,
	max_holds: int,
	already_has: bool,
	copies_total: int,
	copies_available: int,
) -> str | None:
	"""Whether this member may place a hold on a title."""
	if standing:
		return standing
	if max_holds and holds >= max_holds:
		return "hold_limit"
	if already_has:
		return "hold_have"
	if copies_total < 1:
		return "hold_none"
	if copies_available > 0:
		return "hold_available"
	return None


def normal_id(text: str) -> str:
	"""A member's ID number as compared: upper case, without spaces, dashes or slashes ("cs-21/045" = "CS21045")."""
	return "".join(c for c in (text or "").upper() if c.isalnum())


def match_level(roster: dict, given_dob: date | None, given_email: str) -> str:
	"""How well what a person typed matches a roster row: "strong" (the date of birth), "weak" (only the
	email the library has on file) or "" (neither). An email is typed by anyone and nobody has checked it,
	so it never makes a member by itself: a "weak" match waits for a librarian."""
	dob = roster.get("date_of_birth")
	if given_dob and dob and given_dob == dob:
		return "strong"
	email = (roster.get("email") or "").strip().lower()
	if given_email and email and given_email.strip().lower() == email:
		return "weak"
	return ""
