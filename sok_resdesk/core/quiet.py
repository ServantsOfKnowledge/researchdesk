"""Quiet hours: is background work allowed right now? Pure Python."""

from __future__ import annotations

import datetime as dt


def minutes(value) -> int | None:
	"""'09:30', '09:30:00', a time or a timedelta (what Frappe returns for Time fields) → minutes."""
	if value in (None, ""):
		return None
	if isinstance(value, dt.timedelta):
		return int(value.total_seconds() // 60) % (24 * 60)
	if isinstance(value, dt.time):
		return value.hour * 60 + value.minute
	parts = str(value).split(":")
	return (int(parts[0]) * 60 + int(parts[1] if len(parts) > 1 else 0)) % (24 * 60)


def in_quiet_hours(now: dt.datetime, start, end, weekdays_only: bool = False) -> bool:
	"""True between start and end (end earlier than start = overnight). Equal times = never."""
	a, b = minutes(start), minutes(end)
	if a is None or b is None or a == b:
		return False
	m = now.hour * 60 + now.minute
	if a < b:
		inside, day = a <= m < b, now
	else:  # overnight: the part after midnight belongs to the day it started
		inside = m >= a or m < b
		day = now if m >= a else now - dt.timedelta(days=1)
	if inside and weekdays_only and day.weekday() >= 5:
		return False
	return inside
