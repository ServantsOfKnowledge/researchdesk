"""Held jobs: background work that is paused rather than cancelled.

"Pause All" on the Background Jobs page (and "Hold" on a single queued job) takes Research
Desk jobs out of the queue and keeps them in RD Settings (`held_jobs`), so nothing is lost and
Resume puts them back. Jobs that start while everything is paused hold themselves (see
`hold_when_paused`), so new work waits too.

Ingest and push runs are paused differently: they keep the books they haven't done on the run
itself and carry on from there when resumed (see ingest.py / outbound.py).
"""

from __future__ import annotations

import functools
import json
import uuid

import frappe
from frappe.utils import cint, now_datetime

SETTINGS = "RD Settings"


def is_paused() -> bool:
	"""Pause All is on. Read from the database (not cache) so every worker agrees at once."""
	row = frappe.db.sql(
		"select value from `tabSingles` where doctype=%s and field='pause_background'", SETTINGS
	)
	return bool(row and cint(row[0][0]))


def _locked_list() -> list[dict]:
	"""The held-jobs list, row-locked until the transaction ends."""
	row = frappe.db.sql(
		"select value from `tabSingles` where doctype=%s and field='held_jobs' for update", SETTINGS
	)
	try:
		return json.loads(row[0][0]) if row and row[0][0] else []
	except ValueError:
		return []


def _save_list(items: list[dict]) -> None:
	frappe.db.set_single_value(SETTINGS, "held_jobs", json.dumps(items, default=str) if items else "")


def held_jobs() -> list[dict]:
	row = frappe.db.sql("select value from `tabSingles` where doctype=%s and field='held_jobs'", SETTINGS)
	try:
		return json.loads(row[0][0]) if row and row[0][0] else []
	except ValueError:
		return []


def hold(
	method: str,
	kwargs: dict,
	queue: str = "long",
	timeout: int | None = None,
	job_id: str | None = None,
	kind: str = "",
) -> str:
	"""Keep a job to run later. Returns its key in the held list."""
	key = uuid.uuid4().hex[:10]
	items = _locked_list()
	items.append(
		{
			"key": key,
			"method": method,
			"kwargs": kwargs,
			"queue": queue,
			"timeout": timeout,
			"job_id": job_id,
			"kind": kind,
			"held_on": str(now_datetime())[:19],
		}
	)
	_save_list(items)
	frappe.db.commit()
	return key


def release(keys: list[str] | None = None, discard: bool = False) -> int:
	"""Put held jobs back in the queue (all of them when keys is None), or drop them."""
	items = _locked_list()
	chosen = [i for i in items if keys is None or i["key"] in keys]
	_save_list([i for i in items if i not in chosen])
	frappe.db.commit()
	if not discard:
		for i in chosen:
			frappe.enqueue(
				i["method"],
				queue=i.get("queue") or "long",
				timeout=i.get("timeout") or None,
				job_id=i.get("job_id") or None,
				**(i.get("kwargs") or {}),
			)
	return len(chosen)


def hold_when_paused(queue: str = "long", kind: str = ""):
	"""Decorator for background-job functions: while Pause All is on, a job that starts is put
	on hold instead of running. Calls made directly (CLI, tests) always run."""

	def wrap(fn):
		@functools.wraps(fn)
		def inner(*args, **kwargs):
			from rq import get_current_job

			path = f"{fn.__module__}.{fn.__name__}"
			job = get_current_job()
			target = (job.kwargs or {}).get("job_name") or (job.kwargs or {}).get("method") if job else None
			# only the job's own entry point is held, never a call made from inside another job
			if target == path and not args and is_paused():
				timeout = job.timeout if isinstance(job.timeout, int) else None
				hold(
					path,
					kwargs,
					queue=queue,
					timeout=timeout,
					job_id=job.id.split("||", 1)[-1] if job.id else None,
					kind=kind,
				)
				return None
			return fn(*args, **kwargs)

		return inner

	return wrap
