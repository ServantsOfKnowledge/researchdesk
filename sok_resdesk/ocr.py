"""OCR quality of the catalogue: every book's page text scored 0-100 (core/ocrquality.py), so the
worst books can be found and given better OCR or proofreading first.

New and re-indexed books are scored as they are indexed (search.IndexBuffer). Books already in
the catalogue are scored from the page text kept on this server (the page-text cache), without
going back to archive.org; books whose text isn't kept get a score when they are next indexed.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from sok_resdesk.holding import hold_when_paused

MANAGERS = ("System Manager", "ResDesk Manager")
BATCH = 200


def unscored(limit: int = 0) -> list[str]:
	"""Books with page text and no score yet. Frappe keeps whole-number fields at 0, never empty, so
	"not scored" is a quality of 0 with no low pages: a book that really scores 0 has at least one
	low page."""
	return frappe.get_all(
		"RD Item",
		filters={"has_page_text": 1, "ocr_quality": 0, "ocr_low_pages": 0},  # -1: no page text kept
		pluck="name",
		order_by="creation asc",
		limit=limit or None,
	)


@frappe.whitelist()
def enqueue_scoring(limit: int = 0) -> int:
	"""Score the books that have no OCR quality yet, in the background. Returns how many."""
	frappe.only_for(MANAGERS)
	return queue_scoring(cint(limit))


def queue_scoring(limit: int = 0) -> int:
	"""Start scoring in the background: one job that works through the unscored books and queues
	itself again until none are left (queueing a job per batch for a big catalogue filled the job
	queue and was refused). Returns how many books are waiting to be scored."""
	waiting = len(unscored(limit))
	if waiting:
		frappe.enqueue(
			"sok_resdesk.ocr.score_some",
			queue="long",
			timeout=3600,
			job_id="resdesk-ocr-score",
			deduplicate=True,
		)
	return waiting


@hold_when_paused("long")
def score_some(limit: int = 5000) -> int:
	"""Score up to `limit` books, a batch at a time, then queue the next round if any are left."""
	done = 0
	while done < limit:
		if frappe.cache.get_value("resdesk:stop-background"):
			return done
		names = unscored(BATCH)
		if not names:
			return done
		scored = score_batch(names)
		done += len(names)
		if not scored:
			# none of these has page text kept here: mark them so they aren't taken again; they are
			# scored when they are next indexed
			frappe.db.sql(
				"update `tabRD Item` set ocr_low_pages = -1 where name in %s and ocr_quality = 0",
				(tuple(names),),
			)
			frappe.db.commit()
	if unscored(1):
		frappe.enqueue(
			"sok_resdesk.ocr.score_some",
			queue="long",
			timeout=3600,
			job_id="resdesk-ocr-score",
			enqueue_after_commit=True,
		)
	return done


@hold_when_paused("long")
def score_batch(names: list[str]) -> int:
	"""Score books from their kept page text. Returns how many were scored."""
	from sok_resdesk.ingest import read_cached_pages
	from sok_resdesk.search import quality_fields

	scored = 0
	for name in names:
		pages = read_cached_pages(name)
		values = quality_fields(pages) if pages else {}
		if values:
			frappe.db.set_value("RD Item", name, values, update_modified=False)
			scored += 1
		else:
			# no usable page text kept here: marked (-1) so it isn't taken again; it is scored the
			# next time it is indexed
			frappe.db.set_value("RD Item", name, "ocr_low_pages", -1, update_modified=False)
	frappe.db.commit()
	return scored


def progress() -> dict:
	"""For Background Jobs → Machine: books with page text, how many are scored."""
	with_text = frappe.db.count("RD Item", {"has_page_text": 1})
	scored = frappe.db.count("RD Item", {"has_page_text": 1, "ocr_quality": (">", 0)})
	no_text = frappe.db.count("RD Item", {"has_page_text": 1, "ocr_low_pages": -1})
	return {
		"with_text": with_text,
		"scored": scored,
		"no_text_kept": no_text,
		"waiting": max(0, with_text - scored - no_text),
	}


def daily() -> None:
	"""Scheduler: score what is still unscored, a few thousand books a day (cheap: no network)."""
	queue_scoring()
