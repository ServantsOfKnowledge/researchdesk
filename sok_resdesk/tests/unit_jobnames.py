"""What a worker is doing, in words (core/jobnames.py)."""

from sok_resdesk.core.jobnames import LABELS, label


def test_known_jobs_have_plain_words():
	assert label("sok_resdesk.search_queue.send_pending") == "sending page text to the search engine"
	assert label("sok_resdesk.ingest.run_batch") == "ingesting a batch of books"
	assert label("sok_resdesk.ocr.score_some") == "scoring OCR quality"


def test_unknown_jobs_are_spelled_out():
	assert label("sok_resdesk.something.reindex_the_moon") == "reindex the moon"
	assert label("") == "working"
	assert label(None) == "working"


def test_every_listed_job_is_a_function_name_that_exists_somewhere():
	"""A renamed function would silently lose its words: each key is still defined in the app."""
	import re
	from pathlib import Path

	app = Path(__file__).resolve().parents[1]
	source = "\n".join(p.read_text(encoding="utf-8") for p in app.glob("*.py"))
	for name in LABELS:
		assert re.search(rf"^def {name}\(", source, re.M), name
