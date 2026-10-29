"""Periodicals: when the next issues are due, what to call them, which are late. Pure Python."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

FREQUENCIES = {
	"Weekly": ("days", 7),
	"Fortnightly": ("days", 14),
	"Monthly": ("months", 1),
	"Bimonthly": ("months", 2),
	"Quarterly": ("months", 3),
	"Half-yearly": ("months", 6),
	"Yearly": ("months", 12),
}


def add_months(day: date, months: int) -> date:
	"""`day` plus whole months, the day of the month kept as far as the month allows (31 Jan + 1 = 28/29 Feb)."""
	total = day.year * 12 + day.month - 1 + months
	year, month = divmod(total, 12)
	month += 1
	return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def step(day: date, frequency: str, times: int = 1) -> date:
	unit, n = FREQUENCIES[frequency]
	return day + timedelta(days=n * times) if unit == "days" else add_months(day, n * times)


def expected_dates(first: date, frequency: str, count: int) -> list[date]:
	"""The dates of `count` issues, the first on `first`. Monthly issues keep their day (the 15th stays the 15th)."""
	if frequency not in FREQUENCIES:
		raise ValueError(frequency)
	return [step(first, frequency, i) for i in range(max(int(count), 0))]


def label(day: date, frequency: str) -> str:
	"""A name for an issue to start from; staff can write the real one (Vol. 12, No. 3)."""
	unit, _n = FREQUENCIES[frequency]
	return f"{day:%d %b %Y}" if unit == "days" else f"{day:%B %Y}"


def is_late(expected: date, today: date, claim_after_days: int) -> bool:
	"""An issue that has not come this many days after it was due should be claimed from the vendor."""
	return (today - expected).days > max(int(claim_after_days or 0), 0)
