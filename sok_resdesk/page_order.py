"""Putting each page's text next to its own image, for books brought in before 0.24.1.

archive.org's OCR counts every leaf scanned; its page images count only the pages the book
shows (core/scandata.py). Books whose scan left a leaf out (a colour card, a blank cover) had
their text one page off from that leaf on. Each book is checked once, against its scan data:

* no leaf left out (most books): nothing changes;
* otherwise its text is fetched again in the right order, the notes readers made on its text
  move with their words, and its pages are sent to search again.

A book is put right the first time anyone opens its pages (ingest._source_pages), and the rest
in the background, at archive.org's pace (one request a book, two more for a book that moves).
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from sok_resdesk.holding import hold_when_paused

BATCH = 100
JOB = "resdesk-page-order"


def _mark(item_id: str, value: int) -> None:
	frappe.db.set_value("RD Item", item_id, "page_order", value, update_modified=False)


def fix_book(item_id: str, cached: list[dict] | None = None, ia=None) -> list[dict]:
	"""Check one book's page order and put it right. Returns its pages (as the source has them)."""
	from sok_resdesk.core.ia import IAError
	from sok_resdesk.ingest import PAGE_ORDER, _source_pages, client, read_cached_pages

	cached = read_cached_pages(item_id) if cached is None else cached
	source = frappe.db.get_value("RD Item", item_id, ["source", "has_page_text"], as_dict=True)
	if not source:
		return cached or []
	try:
		if source.source == "Local":
			pages = _source_pages(item_id, refresh=True)  # the folder: quick to read again
		else:
			ia = ia or client()
			data = ia.metadata(item_id)
			files = data.get("files") or []
			leaves = ia.scan_leaves(item_id, files)
			if all(shown for _, shown in leaves):  # no scan data, or nothing left out
				_mark(item_id, PAGE_ORDER)
				frappe.db.commit()
				return cached or []
			pages = _source_pages(item_id, ia, data.get("page_numbers"), refresh=True, files=files)
	except (IAError, OSError, ValueError, frappe.ValidationError):
		frappe.log_error(title=f"Research Desk: page order of {item_id} not checked")
		_mark(item_id, -1)  # not taken again by the background job; the reader shows what it has
		frappe.db.commit()
		return cached or []
	if not pages:
		_mark(item_id, -1)
		frappe.db.commit()
		return cached or []
	moves = _moves(cached or [], pages)
	if moves or cached is None:
		_move_notes(item_id, moves)
		if source.has_page_text:
			frappe.enqueue(
				"sok_resdesk.page_order.reindex_book",
				queue="long",
				timeout=1800,
				item_id=item_id,
				enqueue_after_commit=True,
			)
	_mark(item_id, PAGE_ORDER)
	frappe.db.commit()
	return pages


def _moves(old: list[dict], new: list[dict]) -> dict[int, int]:
	"""{old leaf: new leaf} for the pages whose number changed (found by their text)."""
	where: dict[str, list[int]] = {}
	for p in new:
		where.setdefault(p["text"], []).append(p["leaf"])
	moves = {}
	for p in old:
		found = where.get(p["text"])
		if found:
			leaf = found.pop(0)
			if leaf != p["leaf"]:
				moves[p["leaf"]] = leaf
	return moves


def _move_notes(item_id: str, moves: dict[int, int]) -> None:
	"""Notes on the text go with their page's text; notes on a region of the image stay (they
	were made on the image, which was already right)."""
	if not moves:
		return
	notes = frappe.get_all(
		"RD Annotation",
		filters={"item": item_id, "leaf": ("in", list(moves))},
		fields=["name", "leaf", "region"],
	)
	for n in notes:
		if not n.region:
			frappe.db.set_value("RD Annotation", n.name, "leaf", moves[cint(n.leaf)], update_modified=False)


def reindex_book(item_id: str) -> None:
	"""Send the book and its pages to search again (its old page documents are replaced)."""
	from sok_resdesk import dbretry
	from sok_resdesk.catalogue import item_to_record
	from sok_resdesk.ingest import fetch_pages
	from sok_resdesk.search import index_record

	def work():
		doc = frappe.get_doc("RD Item", item_id)
		if not doc.published:
			return
		index_record(item_to_record(doc), fetch_pages(item_id), replace_pages=True)

	dbretry.run(work)  # a book changed meanwhile (error 1020) is read again, not lost


def waiting(limit: int = 0) -> list[str]:
	return frappe.get_all(
		"RD Item",
		filters={"has_page_text": 1, "page_order": 0},
		pluck="name",
		order_by="creation asc",
		limit=limit or None,
	)


def queue_fixing() -> int:
	"""Start the background check (one job that queues itself again). Returns how many wait."""
	count = len(waiting())
	if count:
		frappe.enqueue(
			"sok_resdesk.page_order.fix_some",
			queue="long",
			timeout=6 * 3600,
			job_id=JOB,
			deduplicate=True,
		)
	return count


@hold_when_paused("long")
def fix_some(limit: int = 2000) -> int:
	done = 0
	while done < limit:
		if frappe.cache.get_value("resdesk:stop-background"):
			return done
		names = waiting(BATCH)
		if not names:
			return done
		for name in names:
			try:
				fix_book(name)
			except Exception:
				frappe.db.rollback()
				frappe.log_error(title=f"Research Desk: page order of {name} not checked")
				_mark(name, -1)
				frappe.db.commit()
		done += len(names)
	if waiting(1):
		frappe.enqueue(
			"sok_resdesk.page_order.fix_some",
			queue="long",
			timeout=6 * 3600,
			job_id=JOB,
			enqueue_after_commit=True,
		)
	return done


def daily() -> None:
	"""A safety net: books brought in by an older worker during the upgrade."""
	queue_fixing()
