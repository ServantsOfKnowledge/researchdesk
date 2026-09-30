"""The book limit: how many books this machine can hold, and stopping new ones at the limit.

Settings → Machine Resources → Book Limit: Automatic (worked out from the CPUs, memory and disk,
core/capacity.py), a number of books chosen by a manager, or no limit. At the limit, ingests
keep updating the books already in the catalogue but add no new ones (docs/server.md#book-limit).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core import capacity as cap

MANAGERS = ("System Manager", "ResDesk Manager")
CACHE_KEY = "resdesk_machine_capacity"
MODES = {"Automatic": "auto", "A number I choose": "custom", "No limit": "none"}


class BookLimitReached(frappe.ValidationError):
	pass


def usage() -> tuple[int, int]:
	"""(books, pages of text) in the catalogue, published or not: they all take space."""
	row = frappe.db.sql(
		"select count(*), coalesce(sum(if(has_page_text=1, ifnull(page_count, 0), 0)), 0) from `tabRD Item`"
	)[0]
	return int(row[0]), int(row[1])


def _memory_fallback() -> int | None:
	"""macOS has no /proc/meminfo (native installs)."""
	import subprocess

	try:
		out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
		return int(out.stdout.strip()) if out.returncode == 0 else None
	except (OSError, ValueError, subprocess.TimeoutExpired):
		return None


def machine() -> dict:
	"""CPUs, memory and disk of the machine the data lives on (Docker: what Docker may use)."""
	from sok_resdesk.jobs import _host

	h = _host()
	if not h.get("mem_total"):
		h["mem_total"] = _memory_fallback()
	return h


def status() -> dict:
	"""The limit, what is used, and what the machine could hold (cached a minute)."""
	s = frappe.db.get_singles_dict("RD Settings")
	mode = MODES.get(s.get("book_limit") or "Automatic", "auto")
	books, pages = usage()
	cached = frappe.cache.get_value(CACHE_KEY)
	if not cached:
		h = machine()
		cached = {"host": {k: h.get(k) for k in ("cpus", "mem_total", "disk_total", "disk_free")}}
		frappe.cache.set_value(CACHE_KEY, cached, expires_in_sec=60)
	h = cached["host"]
	est = cap.estimate(
		h.get("cpus") or 0, h.get("mem_total"), h.get("disk_total"), h.get("disk_free"), books, pages
	)
	limit = cap.limit_units(mode, cint(s.get("book_limit_number")), est, books, pages)
	per_book = cap.pages_per_book(books, pages) + cap.BOOK_UNITS
	used = cap.units(books, pages)
	return {
		"mode": mode,
		"books": books,
		"pages": pages,
		"pages_per_book": round(cap.pages_per_book(books, pages)),
		"limit_units": limit,
		"limit_books": int(limit / per_book) if limit is not None else None,
		"remaining_books": max(0, int((limit - used) / per_book)) if limit is not None else None,
		"percent": (min(999, round(used * 100 / limit)) if limit else 100) if limit is not None else None,
		"full": bool(limit is not None and not cap.room(limit, books, pages)),
		"machine": est,
		"host": h,
	}


def has_room(new_pages: int = 0) -> bool:
	st = status()
	return cap.room(st["limit_units"], st["books"], st["pages"], new_pages)


def check_room(record: dict) -> None:
	"""Called before a new book is added (catalogue.upsert_item)."""
	pages = cint(record.get("page_count")) if record.get("has_page_text") else 0
	if not has_room(pages):
		raise BookLimitReached(
			_(
				"The book limit is reached, so no new books are added (Settings → Machine Resources → Book Limit)."
			)
		)


def health_check() -> dict:
	st = status()
	if st["mode"] == "none":
		m = st["machine"]
		return {
			"key": "capacity",
			"label": _("Book limit"),
			"state": "off",
			"detail": _("no limit; this machine holds about {0} books").format(
				f"{m.get('capacity_books', 0):,}"
			)
			if m.get("known")
			else _("no limit"),
			"link": "/app/rd-settings",
		}
	if st["limit_units"] is None:
		return {
			"key": "capacity",
			"label": _("Book limit"),
			"state": "off",
			"detail": _("unknown for this machine"),
		}
	detail = _("{0} of about {1} books ({2}%)").format(
		f"{st['books']:,}", f"{st['limit_books']:,}", st["percent"]
	)
	if st["full"]:
		return {
			"key": "capacity",
			"label": _("Book limit"),
			"state": "bad",
			"detail": detail + " · " + _("reached: no new books are added"),
			"link": "/app/rd-settings",
		}
	return {
		"key": "capacity",
		"label": _("Book limit"),
		"state": "warn" if st["percent"] >= 90 else "ok",
		"detail": detail,
		"link": "/app/rd-settings",
	}


@frappe.whitelist()
def get_status() -> dict:
	frappe.only_for(MANAGERS + ("ResDesk Cataloguer",))
	return status()
