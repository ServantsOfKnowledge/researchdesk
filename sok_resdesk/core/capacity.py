"""How many books this machine can hold, from its CPUs, memory and disk (no Frappe needed).

Measured on real Servants of Knowledge books (docs/scaling.md): the page-level search index
takes about 16 KB per page on disk and grows to about 1.7 times that while indexing; each book
adds about 180 KB more (book index, page-text cache, catalogue); a server for 50,000 books
(about 9.2 million pages) needs at least 4 CPUs and 16 GB of memory.

Room is counted in *page units*, because a 600-page book costs three times a 200-page one: a
book counts its pages of text plus BOOK_UNITS for everything else. Limits are shown in books at
the library's own average number of pages per book.
"""

from __future__ import annotations

GB = 1024**3
PAGE_DISK = 27_000  # bytes on disk per indexed page, with room for the index to grow while indexing
BOOK_DISK = 180_000  # bytes per book besides its pages: book index, page-text cache, catalogue
PAGE_MEMORY = 1_500  # bytes of memory per indexed page for searching to stay quick
BASE_MEMORY = 3 * GB  # database, web server, workers and search engine with nothing indexed
PAGES_PER_CPU = 2_300_000  # indexed pages one CPU keeps quick to search and to index
DEFAULT_PAGES_PER_BOOK = 184
BOOK_UNITS = BOOK_DISK / PAGE_DISK  # a book without text still costs this many page units
LABELS = {"disk": "disk space", "memory": "memory", "cpu": "CPUs"}


def disk_reserve(disk_total: int) -> int:
	"""Kept free for upgrades (about 6 GB), backups and logs: 5% of the disk, at least 10 GB and
	at most 50 GB."""
	return min(max(10 * GB, int(disk_total * 0.05)), 50 * GB)


def pages_per_book(books: int, pages: int) -> float:
	"""The library's own average once there are enough books to tell, else the measured one."""
	return pages / books if books >= 20 and pages >= books else DEFAULT_PAGES_PER_BOOK


def units(books: int, pages: int) -> float:
	return pages + books * BOOK_UNITS


def estimate(
	cpus: int,
	mem_total: int | None,
	disk_total: int | None,
	disk_free: int | None,
	books: int = 0,
	pages: int = 0,
) -> dict:
	"""What the machine can hold, per resource and overall (the smallest), in page units and books.

	Disk counts what the catalogue already uses plus what is still free, minus a reserve."""
	ppb = pages_per_book(books, pages)
	per_book = ppb + BOOK_UNITS
	used = units(books, pages)
	cap = {}
	if disk_total and disk_free is not None:
		used_disk = pages * PAGE_DISK + books * BOOK_DISK
		cap["disk"] = max(0.0, (used_disk + disk_free - disk_reserve(disk_total)) / PAGE_DISK)
	if mem_total:
		cap["memory"] = max(0.0, (mem_total - BASE_MEMORY) / PAGE_MEMORY)
	if cpus:
		cap["cpu"] = float(cpus * PAGES_PER_CPU)
	if not cap:
		return {"known": False, "used_units": used, "pages_per_book": ppb}
	by = min(cap, key=cap.get)
	return {
		"known": True,
		"by": by,
		"by_label": LABELS[by],
		"capacity_units": cap[by],
		"used_units": used,
		"pages_per_book": round(ppb),
		"books": {k: int(v / per_book) for k, v in cap.items()},
		"capacity_books": int(cap[by] / per_book),
	}


def limit_units(mode: str, custom_books: int, machine: dict, books: int, pages: int) -> float | None:
	"""The limit in page units: the machine's estimate, a number of books chosen in Settings
	(at the library's average size), or None for no limit."""
	if mode == "none":
		return None
	if mode == "custom" and custom_books > 0:
		return custom_books * (pages_per_book(books, pages) + BOOK_UNITS)
	return machine.get("capacity_units") if machine.get("known") else None


def room(limit: float | None, books: int, pages: int, new_pages: int = 0) -> bool:
	"""Is there room for one more book of new_pages pages?"""
	return limit is None or units(books, pages) + new_pages + BOOK_UNITS <= limit
