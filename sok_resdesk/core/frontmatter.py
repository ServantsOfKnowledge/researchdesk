"""Catalogue details printed on a book's title page and the back of it (the imprint, or "technical", page).

Pure rules, no database: look through the OCR text of the first pages for a labelled publisher, place,
year and ISBN, say where each was found and how sure we are. A person checks every value before it is
applied to the book (frontmatter.py).
"""

from __future__ import annotations

import re
from datetime import date

from sok_resdesk.core.contents import digits

FRONT_PAGES = 12  # the title page, its back and what follows: details are looked for here
LABELLED, BARE = 0.9, 0.4  # how sure we are of a value that has its label, or only looks right
FIELDS = ("publisher", "place", "year", "isbn")

PUBLISHER = re.compile(
	r"""(?:printed\s+and\s+)?published\s+by | publishers?(?!['’]s) | publishing\s+house
	| ಪ್ರಕಾಶಕರು | ಪ್ರಕಾಶಕ | ಪ್ರಕಾಶನ | प्रकाशक | प्रकाशन | வெளியீட்டாளர் | பதிப்பாளர் | ప్రచురణకర్త | പ്രസാധകർ""",
	re.I | re.X,
)
PLACE = re.compile(
	r"published\s+(?:at|in)(?!\s+\d) | place\s+of\s+publication | प्रकाशन\s+स्थान",
	re.I | re.X,
)
YEAR = re.compile(
	r"""(?:©|\(c\)|copyright|first\s+published|first\s+edition|first\s+printed|first\s+impression
	| published\s+in | printed\s+in | year\s+of\s+publication
	| ಪ್ರಥಮ\s+ಮುದ್ರಣ | ಮೊದಲ\s+ಮುದ್ರಣ | ಮೊದಲನೆಯ\s+ಮುದ್ರಣ | ಪ್ರಕಟಣೆ
	| प्रथम\s+संस्करण | प्रथम\s+आवृत्ति | प्रकाशन\s+वर्ष)
	[^\d\n]{0,25}?(?<!\d)(\d{4})(?!\d)""",
	re.I | re.X,
)
BARE_YEAR = re.compile(r"^\W*(\d{4})\W*$")
ISBN = re.compile(r"ISBN(?:[- ]?1[03])?\s*[:.]?\s*([0-9Xx][0-9Xx\- ]{8,16}[0-9Xx])", re.I)
SEPARATOR = re.compile(r"^[\s:.\-–—]+")
NO_VALUE = re.compile(r"all rights|reserved|^\W*note\b", re.I)


def valid_isbn(text: str) -> bool:
	"""Whether `text` is an ISBN-10 or ISBN-13 with the right check digit."""
	s = re.sub(r"[\s-]", "", text).upper()
	if re.fullmatch(r"\d{9}[\dX]", s):
		return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s)) % 11 == 0
	if re.fullmatch(r"\d{13}", s):
		return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s)) % 10 == 0
	return False


def _year_ok(value: str) -> bool:
	return value.isdigit() and 1450 <= int(value) <= date.today().year + 1


def _clean(value: str) -> str:
	value = re.sub(r"\s+", " ", value).strip(" \t,;:.-–—_")
	return "" if len(value) < 3 or len(value) > 90 or NO_VALUE.search(value) else value


def _after(line: str, match: re.Match, nxt: str) -> str:
	"""What follows a label on its line, or the next line when the label ends its own."""
	rest = SEPARATOR.sub("", line[match.end() :])
	return rest if rest.strip() else nxt


def _found(field: str, value: str, leaf: int, line: str, sure: float) -> dict:
	return {"field": field, "value": value, "leaf": leaf, "snippet": line.strip()[:160], "confidence": sure}


def _publisher_and_place(value: str) -> tuple[str, str]:
	"""'Sahitya Akademi, New Delhi, 1950' → ('Sahitya Akademi', 'New Delhi'): a short last part with no
	digits after a comma is the place."""
	parts = [p.strip() for p in re.sub(r",?\s*\d{4}\W*$", "", value).split(",") if p.strip()]
	if len(parts) > 1 and len(parts[-1].split()) <= 3 and not re.search(r"\d", parts[-1]):
		return _clean(", ".join(parts[:-1])), _clean(parts[-1])
	return _clean(", ".join(parts)), ""


def read(pages: list[dict]) -> list[dict]:
	"""Details found on the first pages ([{leaf, text}]): at most one value per field, the surest first.

	Each is {"field", "value", "leaf", "snippet", "confidence"}; leaf counts from 0."""
	best: dict[str, dict] = {}

	def offer(found: dict) -> None:
		if found["value"] and (
			found["field"] not in best or found["confidence"] > best[found["field"]]["confidence"]
		):
			best[found["field"]] = found

	for page in pages[:FRONT_PAGES]:
		lines = [ln.strip() for ln in (page.get("text") or "").splitlines() if ln.strip()]
		for i, line in enumerate(lines):
			nxt = lines[i + 1] if i + 1 < len(lines) else ""
			leaf = page["leaf"]
			if m := PUBLISHER.search(line):
				publisher, place = _publisher_and_place(_after(line, m, nxt))
				offer(_found("publisher", publisher, leaf, line, LABELLED))
				if place:
					offer(_found("place", place, leaf, line, LABELLED - 0.2))
			if m := PLACE.search(line):
				offer(_found("place", _clean(_after(line, m, nxt).split(",")[0]), leaf, line, LABELLED))
			if m := YEAR.search(line):
				year = digits(m.group(1))
				if _year_ok(year):
					offer(_found("year", year, leaf, line, LABELLED))
			elif m := BARE_YEAR.match(digits(line)):
				if _year_ok(m.group(1)):
					offer(_found("year", m.group(1), leaf, line, BARE))
			if m := ISBN.search(line):
				if valid_isbn(m.group(1)):
					offer(_found("isbn", m.group(1).strip(), leaf, line, LABELLED))
	return sorted(best.values(), key=lambda f: FIELDS.index(f["field"]))


def _norm(text) -> str:
	return re.sub(r"[\W_]+", "", str(text or "").casefold())


def is_new(field: str, value: str, current) -> bool:
	"""Whether `value` says something the record does not already say (it is empty there, or differs)."""
	have, want = _norm(current), _norm(value)
	if not have:
		return True
	if field in ("publisher", "place"):
		return (
			want not in have and have not in want
		)  # 'Oxford University Press' is 'Oxford University Press, Delhi'
	return have != want
