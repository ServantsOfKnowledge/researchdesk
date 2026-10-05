"""Which of the library's catalogue records is which book here. Pure Python.

A record from the library system (core/marcin.summary) is compared with the books the search
engine finds for it:

1. **It already points to one**: an archive.org address in its 856 that is a book here → certain.
2. **The same ISBN** → certain.
3. **Title, authors and year**, in either script (a record's 880 title in Kannada against a
   book's title, its romanised 245 against a book's other title): a score from 0 to 1. Above
   ``LINK_AT`` the record is linked; between ``PROPOSE_AT`` and that it is proposed for a
   cataloguer to accept or reject; below, it has no match here.
"""

from __future__ import annotations

from sok_resdesk.core.authority import name_similarity
from sok_resdesk.core.review import title_key

LINK_AT = 0.88
ARCHIVE_LINK, SAME_ISBN = "its link to archive.org", "the same ISBN"
UNKNOWN = 0.75  # the score of an author or a year one side doesn't give
PROPOSE_AT = 0.6
STOP = {"of", "and", "the", "a", "an", "in", "on", "to", "for", "with", "by", "vol", "volume", "part", "no"}


def _tokens(title: str) -> set[str]:
	return {w for w in title_key(title).split() if w not in STOP and len(w) > 1}


def title_score(a: str, b: str) -> float:
	if not a or not b:
		return 0.0
	if title_key(a) == title_key(b):
		return 1.0
	ta, tb = _tokens(a), _tokens(b)
	if not ta or not tb:
		return 0.0
	common = len(ta & tb)
	if common == min(len(ta), len(tb)):  # one is the other with a subtitle or a volume
		return 0.9 if common >= 2 else 0.75
	return common / len(ta | tb)


def best_title(rec: dict, book: dict) -> float:
	ours = [book.get("title") or "", book.get("alt_title") or ""]
	theirs = [rec.get("title") or "", rec.get("alt_title") or ""]
	return (
		max(title_score(a, b) for a in theirs for b in ours if a and b) if any(ours) and any(theirs) else 0.0
	)


def author_score(rec: dict, book: dict) -> float | None:
	theirs = rec.get("creators") or []
	ours = (book.get("creators") or []) + (book.get("alt_creators") or [])
	if not theirs or not ours:
		return None  # nothing to compare: neither for nor against
	return max(name_similarity(a, b) for a in theirs for b in ours)


def year_score(rec: dict, book: dict) -> float | None:
	try:
		a, b = int(rec.get("year") or 0), int(book.get("year") or 0)
	except (TypeError, ValueError):
		return None
	if not a or not b:
		return None
	return 1.0 if a == b else 0.6 if abs(a - b) == 1 else 0.0


def score(rec: dict, book: dict) -> dict:
	"""{score, why} for one record and one candidate book."""
	if book.get("item_id") in (rec.get("archive_ids") or []):
		return {"score": 1.0, "why": ARCHIVE_LINK}
	if rec.get("isbn") and rec["isbn"] == (book.get("isbn") or "").replace("-", "").upper():
		return {"score": 0.98, "why": SAME_ISBN}
	title = best_title(rec, book)
	author, year = author_score(rec, book), year_score(rec, book)
	# what can't be compared counts as weak evidence: never as good as authors and a year that agree
	value = (
		0.6 * title
		+ 0.25 * (UNKNOWN if author is None else author)
		+ 0.15 * (UNKNOWN if year is None else year)
	)
	if title < 0.5:  # a different title is never the same book, however alike the rest
		value = min(value, title)
	why = ["title"] + (["authors"] if author is not None else []) + (["year"] if year is not None else [])
	return {"score": round(value, 3), "why": ", ".join(why)}


def best(rec: dict, books: list[dict]) -> list[dict]:
	"""The candidates, best first: [{item_id, title, score, why}]."""
	ranked = []
	for book in books:
		s = score(rec, book)
		ranked.append({"item_id": book.get("item_id"), "title": book.get("title") or "", **s})
	return sorted(ranked, key=lambda r: -r["score"])


def decide(ranked: list[dict]) -> str:
	"""Linked, Proposed or No match, from the best candidates. Two close candidates are a
	question for a person, however good both look."""
	if not ranked or ranked[0]["score"] < PROPOSE_AT:
		return "No match"
	top = ranked[0]["score"]
	runner = ranked[1]["score"] if len(ranked) > 1 else 0.0
	certain = ranked[0]["why"] in (ARCHIVE_LINK, SAME_ISBN)  # identifiers, not likeness
	if certain or (top >= LINK_AT and top - runner >= 0.1):
		return "Linked"
	return "Proposed"
