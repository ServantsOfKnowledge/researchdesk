"""Plain words for what a background worker is doing, from the job's method name. Pure Python.

Background Jobs → Machine shows "1 of 8 workers busy: sending page text · 7 waiting for work".
Methods not listed get their function's name spelled out ("reindex_book" → "reindex book").
"""

from __future__ import annotations

# the function's name (the last part of "sok_resdesk.module.function") → what it is doing
LABELS = {
	"send_pending": "sending page text to the search engine",
	"run_batch": "ingesting a batch of books",
	"plan_run": "planning an ingest run",
	"score_some": "scoring OCR quality",
	"fix_some": "matching page text to page images",
	"reindex_book": "re-indexing a book",
	"reindex_item": "re-indexing a book",
	"rebuild_batch": "rebuilding the search index",
	"update_item_fields": "updating books in the search index",
	"ocr_book": "reading a book's pages with OCR",
	"ocr_page_job": "reading a page again with OCR",
	"reocr_books": "reading books again with OCR",
	"preserve_batch": "making preservation copies",
	"replicate_batch": "making second copies",
	"audit": "checking preserved books (fixity)",
	"export_collection_job": "exporting a collection",
	"refresh_mirrors": "syncing collections with archive.org",
	"run_upload": "giving a book to the Internet Archive",
	"run_send": "sending to Wikimedia",
	"build_plan": "preparing what to send to Wikimedia",
	"run": "running a background task",
	"auto_push": "pushing changed records",
	"scan": "checking records for the review queue",
	"build_job": "building a ground-truth set",
	"apply_visibility": "changing who can see books",
	"recompute": "working out who can see books",
	"apply_rules_now": "applying a collection's rules",
	"assign_missing": "giving books permanent links",
	"point_at_tombstone": "updating DOIs",
	"run_backup": "making a backup",
	"run_export": "exporting the library",
	"apply_plan": "importing a moved library",
	"fill_missing": "fetching collection pictures",
}


def label(method: str) -> str:
	"""What a job with this method path is doing, in English words."""
	name = str(method or "").rsplit(".", 1)[-1]
	if not name:
		return "working"
	return LABELS.get(name) or name.strip("_").replace("_", " ")
