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
	return frappe.get_all(
		"RD Item",
		filters={"has_page_text": 1, "ocr_quality": ("is", "not set")},
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
	names = unscored(limit)
	for n, i in enumerate(range(0, len(names), BATCH), 1):
		frappe.enqueue(
			"sok_resdesk.ocr.score_batch",
			queue="long",
			timeout=3600,
			names=names[i : i + BATCH],
			job_id=f"resdesk-ocr-score-{n}",
		)
	return len(names)


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
	frappe.db.commit()
	return scored


def daily() -> None:
	"""Scheduler: score what is still unscored, a few thousand books a day (cheap: no network)."""
	queue_scoring(limit=5000)
