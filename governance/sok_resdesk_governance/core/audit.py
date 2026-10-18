"""The audit log's chain: each line carries a hash of the line before it. Pure Python, no Frappe.

A line that is changed, or a line that is removed, breaks the chain from there on, and `verify`
says where. Only someone who rewrites every later line (and the database backups) could hide it.
"""

from __future__ import annotations

import hashlib
import hmac

FIRST = "0" * 64
FIELDS = ("seq", "event_time", "user", "event", "item", "detail", "ip_address")


def row_hash(prev: str, row: dict, key: bytes = b"") -> str:
	parts = [prev or FIRST, *(str(row.get(f) if row.get(f) is not None else "") for f in FIELDS)]
	return hmac.new(key, "\x1f".join(parts).encode(), hashlib.sha256).hexdigest()


def verify(rows, key: bytes = b"") -> dict:
	"""rows (any iterable) in order of `seq`. {"ok": True, "checked": n, "last": seq, "head": hash}
	or {"ok": False, "at": seq, "why": ...}."""
	prev, last, i = FIRST, None, -1
	for i, row in enumerate(rows):
		if last is not None and row["seq"] != last + 1:
			return {"ok": False, "at": last + 1, "why": "a line is missing", "checked": i}
		if (row.get("prev_hash") or FIRST) != prev:
			return {"ok": False, "at": row["seq"], "why": "the chain is broken", "checked": i}
		if row_hash(prev, row, key) != row.get("row_hash"):
			return {"ok": False, "at": row["seq"], "why": "the line was changed", "checked": i}
		prev, last = row["row_hash"], row["seq"]
	return {"ok": True, "checked": i + 1, "last": last, "head": prev}
