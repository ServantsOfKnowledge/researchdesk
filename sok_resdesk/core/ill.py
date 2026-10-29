"""Interlibrary loan: which step may follow which. Pure Python.

Borrowing: we ask another library for a book for one of our members.
    Requested → Sent (the request is with the other library) → Received (the book arrived, kept for the
    member) → Lent to Patron → Returned (the member brought it back) → Sent Back → Closed
Lending: another library asks us for one of our books.
    Requested → Approved → Sent (the book is on its way to them) → Returned (it came back) → Closed
Either may end early as Refused or Cancelled while nothing has been sent or received.
"""

from __future__ import annotations

BORROWING, LENDING = "Borrowing", "Lending"

FLOW = {
	BORROWING: {
		"Requested": ("Sent", "Refused", "Cancelled"),
		"Sent": ("Received", "Refused", "Cancelled"),
		"Received": ("Lent to Patron",),
		"Lent to Patron": ("Returned",),
		"Returned": ("Sent Back",),
		"Sent Back": ("Closed",),
	},
	LENDING: {
		"Requested": ("Approved", "Refused"),
		"Approved": ("Sent", "Cancelled"),
		"Sent": ("Returned",),
		"Returned": ("Closed",),
	},
}

CLOSED = ("Closed", "Refused", "Cancelled")


def allowed(direction: str, status: str) -> tuple[str, ...]:
	return FLOW.get(direction, {}).get(status, ())


def can_move(direction: str, status: str, to: str) -> bool:
	return to in allowed(direction, status)


def is_open(status: str) -> bool:
	return status not in CLOSED
