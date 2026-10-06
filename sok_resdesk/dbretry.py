"""Run a piece of database work again when MariaDB refuses it for a transient reason.

A background job that reads a book, spends a while talking to the search engine and then writes
the book back keeps one database snapshot open. If anything else changed that book meanwhile,
MariaDB refuses the write ("Record has changed since last read", error 1020) or picks the job
as a deadlock victim (1213). Nothing is wrong with the data: starting again from a fresh
snapshot works, so that is what this does, a few times, before it gives up.
"""

from __future__ import annotations

import time

import frappe

TRANSIENT_CODES = ("1020", "1205", "1213")


def transient(e: Exception) -> bool:
	text = str(e)
	return (
		isinstance(e, frappe.QueryDeadlockError)
		or frappe.db.is_deadlocked(e)
		or frappe.db.is_timedout(e)
		or any(f"({code}," in text for code in TRANSIENT_CODES)
	)


def run(work, attempts: int = 3, pause: float = 1.0):
	"""work() with a fresh snapshot, committed after; again on a transient refusal."""
	for attempt in range(attempts):
		try:
			frappe.db.commit()  # release the old snapshot before reading
			result = work()
			frappe.db.commit()
			return result
		except Exception as e:
			if not transient(e) or attempt == attempts - 1:
				raise
			frappe.db.rollback()
			time.sleep(pause * (1 + attempt))
