"""How good is a page's OCR text? A score from 0 (garbage) to 100 (clean), from the text alone.

No dictionaries and no page images: it looks at what broken OCR of Indic and Latin scripts
leaves behind, which is enough to find the worst books and pages (what the re-OCR pipeline and
the proofreaders should take first). It is a ranking, not a measure of accuracy against a
correct transcription.

For each word (a run of letters, combining marks and joiners):
* it must be in **one script** (ಕನXಡ, Kannada with a Latin letter inside, is an OCR error);
* in an Indic script it must be **well formed**: it can't start with a vowel sign or a virama,
  and no vowel sign may follow another or follow a virama directly;
* it must be of a **plausible length** (1-letter "words" and 30-letter ones are usually noise).

The page score is the share of well-formed words (weighted by length), lowered by the share of
characters that are neither letters, digits, spaces nor ordinary punctuation (stray symbols,
replacement characters, box-drawing).
"""

from __future__ import annotations

import unicodedata

VERSION = 1  # raise when the scoring changes, so scores can be worked out again
LOW = 50  # a page below this is "low quality"

# (name, first, last) for the scripts the libraries hold
SCRIPTS = (
	("Latin", 0x0041, 0x024F),
	("Devanagari", 0x0900, 0x097F),
	("Bengali", 0x0980, 0x09FF),
	("Gurmukhi", 0x0A00, 0x0A7F),
	("Gujarati", 0x0A80, 0x0AFF),
	("Oriya", 0x0B00, 0x0B7F),
	("Tamil", 0x0B80, 0x0BFF),
	("Telugu", 0x0C00, 0x0C7F),
	("Kannada", 0x0C80, 0x0CFF),
	("Malayalam", 0x0D00, 0x0D7F),
)
INDIC = {name for name, _a, _b in SCRIPTS if name != "Latin"}
JOINERS = {"‌", "‍"}  # ZWNJ / ZWJ, legitimate inside Indic words
PUNCT = set(".,;:!?'\"()[]{}-–—/«»“”‘’…॥।*&%+=<>#@_|~^`$")


def script_of(ch: str) -> str | None:
	cp = ord(ch)
	for name, first, last in SCRIPTS:
		if first <= cp <= last:
			return name
	return None


def _is_sign(ch: str) -> bool:
	"""A dependent vowel sign or other combining mark (matra, anusvara, nukta…)."""
	return unicodedata.category(ch) in ("Mn", "Mc")


def _kind(ch: str) -> str:
	"""vowel (a dependent vowel sign), virama, mark (anusvara, visarga, candrabindu, nukta) or letter."""
	name = unicodedata.name(ch, "")
	if "VOWEL SIGN" in name:
		return "vowel"
	if name.endswith("SIGN VIRAMA"):
		return "virama"
	if _is_sign(ch):
		return "mark"
	return "letter"


def _words(text: str):
	word = ""
	for ch in text:
		if ch.isalpha() or _is_sign(ch) or ch in JOINERS:
			word += ch
		else:
			if word:
				yield word
			word = ""
	if word:
		yield word


def word_ok(word: str) -> tuple[bool, str | None]:
	"""(well formed, script) for one word."""
	scripts = {s for s in (script_of(c) for c in word if c not in JOINERS) if s}
	if len(scripts) != 1:
		return False, None  # mixed scripts, or letters outside the scripts we know
	script = scripts.pop()
	letters = sum(1 for c in word if c.isalpha())
	if script in INDIC:
		kinds = [_kind(c) for c in word if c not in JOINERS]
		if kinds[0] != "letter":
			return False, script  # a word can't start with a vowel sign, virama or mark
		for prev, kind in zip(kinds, kinds[1:], strict=False):
			# two vowel signs in a row, a vowel sign after a virama, a virama after a vowel sign
			if (prev, kind) in (
				("vowel", "vowel"),
				("virama", "vowel"),
				("virama", "virama"),
				("vowel", "virama"),
			):
				return False, script
		if not 1 <= letters <= 25:
			return False, script
	else:
		if not 2 <= len(word) <= 25 and word.lower() not in ("a", "i", "o"):
			return False, script
		vowels = sum(1 for c in word.lower() if c in "aeiouy")
		if len(word) > 4 and vowels == 0:
			return False, script  # "xkcdtrw": a consonant pile, not a word
	return True, script


def page_quality(text: str) -> dict:
	"""{score 0-100, words, script (the main one), chars}. An empty page has no score (None)."""
	text = text or ""
	good = total = 0
	by_script: dict[str, int] = {}
	for word in _words(text):
		ok, script = word_ok(word)
		weight = len(word)
		total += weight
		if ok:
			good += weight
		if script:
			by_script[script] = by_script.get(script, 0) + weight
	visible = [c for c in text if not c.isspace()]
	if not visible or not total:
		return {"score": None, "words": 0, "script": None, "chars": len(visible)}
	junk = sum(
		1
		for c in visible
		if not (c.isalnum() or _is_sign(c) or c in JOINERS or c in PUNCT or unicodedata.category(c) == "Nd")
	)
	word_share = good / total
	junk_share = junk / len(visible)
	score = round(100 * word_share * max(0.0, 1 - 2 * junk_share))
	main = max(by_script, key=by_script.get) if by_script else None
	return {"score": max(0, min(100, score)), "words": total, "script": main, "chars": len(visible)}


def book_quality(pages: list[dict]) -> dict:
	"""{score, low_pages, scored_pages, script} for a book's pages ([{text}]): the score is the
	pages' scores weighted by how much text each has, so a near-empty page doesn't count much."""
	weighted = weight = low = scored = 0
	scripts: dict[str, int] = {}
	for page in pages or []:
		q = page_quality(page.get("text") or "")
		if q["score"] is None:
			continue
		scored += 1
		weighted += q["score"] * q["words"]
		weight += q["words"]
		low += q["score"] < LOW
		if q["script"]:
			scripts[q["script"]] = scripts.get(q["script"], 0) + q["words"]
	if not weight:
		return {"score": None, "low_pages": 0, "scored_pages": 0, "script": None}
	return {
		"score": round(weighted / weight),
		"low_pages": low,
		"scored_pages": scored,
		"script": max(scripts, key=scripts.get) if scripts else None,
	}
