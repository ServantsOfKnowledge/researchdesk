"""Known errors: what an Error Log entry means and which release fixed it (pure, no Frappe).

Server → Logs → Log QA matches each entry to this list and says whether it is safe to ignore:
logged before the fix was installed (resolved), still possible because the release is not
installed yet (upgrade), or logged after the fix (recurring: the fix did not stop it, look).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Known:
	key: str
	pattern: str  # a regular expression, matched case-insensitively against the entry's title and text
	title: str
	fixed_in: str
	note: str
	info: bool = False  # not a fault: a record of something repaired by itself


KNOWN: tuple[Known, ...] = (
	Known(
		"rq-created-at",
		r"b'created_at'",
		"Page-text sender: a stopped run left a damaged job record",
		"0.68.6",
		"Send now (and the ten-minute turn) failed with KeyError created_at. The record is cleared and the sender queued again.",
	),
	Known(
		"sender-record-cleared",
		r"page-text sender's old record was damaged",
		"Page-text sender: damaged record cleared by itself",
		"0.68.6",
		"Not a fault: this is the repair noting what it did.",
		info=True,
	),
	Known(
		"default-mail-account",
		r"there_must_be_only_one_default",
		"Saving the email settings failed (another default mail account)",
		"0.68.3",
		"Another default mail account with a wrong setting made the save fail. Other accounts now just lose the default.",
	),
	Known(
		"record-changed",
		r"Record has changed since last read|\(1020",
		"Page text or a reindex failed: the book changed meanwhile (error 1020)",
		"0.65.1",
		"The book is read again from a fresh snapshot, up to three tries.",
	),
	Known(
		"signal-main-thread",
		r"signal only works in main thread",
		"Pause, Stop or the jobs list failed (signal only works in main thread)",
		"0.19.1",
		"Listing jobs now only reads; the ten-minute watcher does the clean-up.",
	),
	Known(
		"query-too-long",
		r"Data too long for column 'query'",
		"A long identifier list failed (Data too long for column 'query')",
		"0.33.0",
		"A long list is taken as the run's books instead of one archive.org search.",
	),
)


def version_tuple(v: str) -> tuple[int, ...]:
	nums = re.findall(r"\d+", v or "")
	return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def at_least(installed: str, wanted: str) -> bool:
	return version_tuple(installed) >= version_tuple(wanted)


def match(*texts: str) -> Known | None:
	"""The known error these texts (an entry's title, method and text) describe, or None."""
	blob = "\n".join(t for t in texts if t)
	for k in KNOWN:
		if re.search(k.pattern, blob, re.IGNORECASE):
			return k
	return None


def fix_active_since(history: list[tuple[str, str]], fixed_in: str) -> str | None:
	"""When a version with the fix first became the installed one: the earliest history entry
	(version, ISO time) at or past `fixed_in`, or None when there is none."""
	times = sorted(ts for v, ts in history if at_least(v, fixed_in))
	return times[0] if times else None


def verdict(known: Known, installed: str, created: str, history: list[tuple[str, str]]) -> str:
	"""resolved: logged before the fix was installed, safe to ignore.
	upgrade: the fix is in a release not installed yet.
	recurring: logged after the fix was installed: the fix did not stop it.
	unsure: the fix is installed but there is no record of when.
	info: not a fault, a note of something repaired by itself."""
	if known.info:
		return "info"
	if not at_least(installed, known.fixed_in):
		return "upgrade"
	since = fix_active_since(history, known.fixed_in)
	if since is None:
		return "unsure"
	return "resolved" if str(created) < since else "recurring"
