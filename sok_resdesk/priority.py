"""Worker priority: how much CPU the background workers get compared with everything else.

A manager chooses it live on Background Jobs → Machine (*Worker priority*); it is stored in
RD Settings (*Worker Priority (nice)*) and every worker applies it to itself, between two books,
with `setpriority`. Nothing has to be restarted to make the workers *nicer*. Making them
*less* nice needs the permission to do so: Docker installs get it from `ulimits: nice` in
compose.yaml; elsewhere a worker that may not says so on the page, and the level then needs
`./resdesk.sh resources set WORKER_NICE=<n>` (which restarts the workers at that level).

nice: 19 is the lowest priority (the workers only use what the portal, search and database leave),
0 is the same as everything else, negative is above it.
"""

from __future__ import annotations

import os
import socket
import time

import frappe
from frappe import _
from frappe.utils import cint

MANAGERS = ("System Manager", "ResDesk Manager")
SEEN_KEY = "resdesk:worker-priority"
LEVELS = (  # (nice, name) as the Desk offers them
	(19, "Lowest: only what the portal leaves over"),
	(10, "Low"),
	(5, "Medium"),
	(0, "Normal: the same as the portal and search"),
	(-5, "High: ahead of the portal"),
)
MIN_NICE, MAX_NICE = -20, 19
OPTIONS = [str(n) for n, _label in LEVELS]  # what Settings → Worker Priority offers
_THROTTLE = 5.0  # seconds between looks at the setting, per process
_checked = 0.0


def wanted() -> int | None:
	"""The level chosen in the Desk, or None when none was (workers stay as they were started)."""
	value = frappe.db.get_single_value("RD Settings", "worker_nice", cache=False)
	if value in (None, ""):
		return None
	return max(MIN_NICE, min(MAX_NICE, cint(value)))


def current() -> int | None:
	try:
		return os.getpriority(os.PRIO_PROCESS, 0)
	except (AttributeError, OSError):
		return None  # not on this system (Windows)


def _remember(level: int | None, wanted_level: int | None, error: str = "") -> None:
	"""Tell the Desk where this worker stands (shown on Background Jobs → Machine)."""
	try:
		frappe.cache.hset(
			SEEN_KEY,
			f"{socket.gethostname()}:{os.getppid()}",
			{"nice": level, "wanted": wanted_level, "at": time.time(), "error": error},
		)
	except Exception:
		pass  # a worker's priority is never worth stopping work for


def apply(force: bool = False) -> int | None:
	"""Called by a worker between two books: take on the level chosen in the Desk. Cheap (the
	setting is looked at every few seconds at most). Returns the level it now runs at."""
	global _checked
	now = time.monotonic()
	if not force and now - _checked < _THROTTLE:
		return None
	_checked = now
	try:
		target = wanted()
		have = current()
		if target is None or have is None:
			return have
		if target != have:
			try:
				os.setpriority(os.PRIO_PROCESS, 0, target)
			except OSError as e:
				_remember(have, target, str(e))
				return have
		_remember(target, target)
		return target
	except Exception:
		return None


def workers_seen(max_age: int = 900) -> list[dict]:
	"""Workers that reported in lately: {nice, wanted, error}. Each one reports when it starts a
	book, so an idle worker shows its last book's level until the next one."""
	try:
		rows = frappe.cache.hgetall(SEEN_KEY) or {}
	except Exception:
		return []
	cutoff = time.time() - max_age
	return [v for v in rows.values() if isinstance(v, dict) and v.get("at", 0) >= cutoff]


def status() -> dict:
	"""For Background Jobs → Machine."""
	seen = workers_seen()
	target = wanted()
	return {
		"wanted": target,
		"levels": [{"nice": n, "label": _(label)} for n, label in LEVELS],
		"workers": len(seen),
		"applied": sum(1 for w in seen if target is not None and w.get("nice") == target),
		"refused": sorted({w["error"] for w in seen if w.get("error")}),
	}


@frappe.whitelist()
def set_worker_priority(nice: int | str) -> dict:
	"""Choose the workers' priority (nice level, 19 lowest … -20 highest). Takes effect as each
	worker starts its next book; an idle worker takes it on with its next job."""
	frappe.only_for(MANAGERS)
	try:
		level = int(nice)
	except (TypeError, ValueError):
		level = None
	if level is None or str(level) not in OPTIONS:
		frappe.throw(_("Choose one of: {0}.").format(", ".join(OPTIONS)))
	frappe.db.set_single_value("RD Settings", "worker_nice", str(level))
	frappe.db.commit()
	return {
		**status(),
		"message": _(
			"Worker priority set to {0}. Each worker takes it on when it starts its next book."
		).format(level),
	}
