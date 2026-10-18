"""Retention: when a record is due for disposal, and which rule governs it. Pure Python, no Frappe.

A rule says how many years a record is kept, counted from the year of the record or from the day it
was added, and what then happens to it. When several rules match one record the longest period
governs (a tie goes to the more cautious action), so adding a rule can never shorten a record's life
by accident. Nothing is ever disposed of from here: a due record is only listed for a person to approve.
"""

from __future__ import annotations

from datetime import date

BASIS = ("Year of the record", "Date added")
ACTIONS = ("Review only", "Transfer to archives", "Destroy")  # most cautious first


def due_on(basis: str, years: int, year: int | None, added: date) -> date | None:
	"""The day the record's period ends; None when the basis cannot be worked out (no year)."""
	try:
		if basis == "Year of the record":
			return date(int(year) + int(years), 12, 31) if year else None
		try:
			return added.replace(year=added.year + int(years))
		except ValueError:  # 29 February
			return added.replace(year=added.year + int(years), day=28)
	except (ValueError, OverflowError):  # a year or period no date can hold
		return None


def governing(candidates: list[tuple[str, date, str]]) -> tuple[str, date, str] | None:
	"""(rule, due, action) with the latest due date; the more cautious action on a tie, then the name."""
	if not candidates:
		return None
	return max(candidates, key=lambda c: (c[1], -ACTIONS.index(c[2]), c[0]))
