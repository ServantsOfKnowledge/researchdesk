"""Metadata normalisation for Internet Archive records.

Pure Python (no Frappe imports) so it can be unit-tested and reused by other
sources. IA metadata is messy: languages come as "Kan", "kan", "Kannada",
"KAN"; dates default to "YYYY-01-01"; creators are strings or lists, sometimes
joined with ";". Everything that reaches the catalogue passes through here.
"""

from __future__ import annotations

import re
from typing import Any

# ISO 639-3 code -> English label. Covers what appears in SOK and common Indic
# holdings; unknown values are kept as-is so nothing is lost.
LANGUAGES: dict[str, str] = {
	"eng": "English",
	"kan": "Kannada",
	"hin": "Hindi",
	"kok": "Konkani",
	"ory": "Odia",
	"tam": "Tamil",
	"mal": "Malayalam",
	"tel": "Telugu",
	"san": "Sanskrit",
	"mar": "Marathi",
	"ben": "Bengali",
	"guj": "Gujarati",
	"pan": "Punjabi",
	"urd": "Urdu",
	"tcy": "Tulu",
	"kfa": "Kodava",
	"asm": "Assamese",
	"nep": "Nepali",
	"pli": "Pali",
	"pra": "Prakrit",
	"ara": "Arabic",
	"per": "Persian",
	"fre": "French",
	"ger": "German",
	"por": "Portuguese",
	"lat": "Latin",
	"rus": "Russian",
	"spa": "Spanish",
	"jpn": "Japanese",
	"chi": "Chinese",
	"mul": "Multiple languages",
}

# Variant spellings seen in the wild -> ISO 639-3
_LANGUAGE_ALIASES: dict[str, str] = {
	"en": "eng",
	"english": "eng",
	"kn": "kan",
	"kannada": "kan",
	"kanada": "kan",
	"hi": "hin",
	"hindi": "hin",
	"konkani": "kok",
	"or": "ory",
	"ori": "ory",
	"oriya": "ory",
	"odia": "ory",
	"ta": "tam",
	"tamil": "tam",
	"ml": "mal",
	"malayalam": "mal",
	"te": "tel",
	"telugu": "tel",
	"sa": "san",
	"sanskrit": "san",
	"mr": "mar",
	"marathi": "mar",
	"bn": "ben",
	"bengali": "ben",
	"bangla": "ben",
	"gu": "guj",
	"gujarati": "guj",
	"pa": "pan",
	"punjabi": "pan",
	"ur": "urd",
	"urdu": "urd",
	"tulu": "tcy",
	"kodava": "kfa",
	"coorgi": "kfa",
	"as": "asm",
	"assamese": "asm",
	"ne": "nep",
	"nepali": "nep",
	"pali": "pli",
	"ar": "ara",
	"arabic": "ara",
	"fa": "per",
	"fas": "per",
	"persian": "per",
	"fr": "fre",
	"fra": "fre",
	"french": "fre",
	"de": "ger",
	"deu": "ger",
	"german": "ger",
	"pt": "por",
	"portuguese": "por",
	"la": "lat",
	"latin": "lat",
	"ru": "rus",
	"russian": "rus",
	"es": "spa",
	"spanish": "spa",
	"ja": "jpn",
	"japanese": "jpn",
	"zh": "chi",
	"zho": "chi",
	"chinese": "chi",
}

YEAR_RE = re.compile(r"(1[0-9]{3}|20[0-9]{2})")
SPLIT_RE = re.compile(r"\s*;\s*")


def as_list(value: Any) -> list[str]:
	"""IA fields may be a string, a list, or missing. Always return a clean list."""
	if value is None:
		return []
	if isinstance(value, (list, tuple)):
		items = value
	else:
		items = [value]
	out: list[str] = []
	for item in items:
		if item is None:
			continue
		for part in SPLIT_RE.split(str(item)):
			part = clean_text(part)
			if part and part not in out:
				out.append(part)
	return out


def first(value: Any) -> str:
	values = as_list(value)
	return values[0] if values else ""


def clean_text(value: Any) -> str:
	if value is None:
		return ""
	text = str(value).replace(" ", " ")
	text = re.sub(r"<[^>]+>", " ", text)  # IA descriptions often carry HTML
	return re.sub(r"\s+", " ", text).strip()


def normalize_language(value: Any) -> tuple[str, str]:
	"""Return (code, label). Multiple languages -> ("mul", "Kannada; English")."""
	codes: list[str] = []
	for raw in as_list(value):
		key = raw.strip().lower()
		code = _LANGUAGE_ALIASES.get(key, key if key in LANGUAGES else "")
		if not code:
			code = raw.strip()
		if code not in codes:
			codes.append(code)
	if not codes:
		return "", ""
	if len(codes) == 1:
		return codes[0], LANGUAGES.get(codes[0], codes[0])
	return "mul", "; ".join(LANGUAGES.get(c, c) for c in codes)


def parse_year(value: Any) -> int | None:
	match = YEAR_RE.search(first(value))
	return int(match.group(1)) if match else None


def decade_of(year: int | None) -> str:
	return f"{year // 10 * 10}s" if year else ""


def public_collections(value: Any) -> list[str]:
	"""Drop IA's per-user favourites ("fav-*") which are not real collections."""
	return [c for c in as_list(value) if not c.lower().startswith("fav-")]


def is_restricted(meta: dict) -> bool:
	flag = str(meta.get("access-restricted-item", "")).lower()
	return flag in ("true", "1", "yes")


ITEM_TYPES = ("Book", "Periodical", "Article", "Thesis", "Report", "Manuscript", "Map", "Other")

_TYPE_HINTS = (
	(
		"Periodical",
		("periodical", "magazine", "journal", "newspaper", "patrika", "ಪತ್ರಿಕೆ", "gazette", "bulletin"),
	),
	("Thesis", ("thesis", "dissertation", "ph.d", "phd")),
	("Manuscript", ("manuscript", "palm leaf", "palm-leaf", "ಹಸ್ತಪ್ರತಿ", "ತಾಳೆಗರಿ")),
	("Report", ("annual report", "report of", "proceedings")),
	("Map", ("map", "atlas")),
)


def guess_item_type(meta: dict) -> str:
	"""Best guess of what kind of document this is. IA calls everything 'texts', so we look
	at the title, subjects and collections for hints; anything unclear is a Book."""
	haystack = " ".join(
		as_list(meta.get("subject"))
		+ as_list(meta.get("collection"))
		+ [first(meta.get("title"))]
		+ as_list(meta.get("type"))
	).lower()
	for kind, words in _TYPE_HINTS:
		if any(w in haystack for w in words):
			return kind
	return "Book"


def normalize_ia_item(identifier: str, meta: dict, files: list[dict] | None = None) -> dict:
	"""Map one IA metadata record to the RD Item shape used by the catalogue."""
	files = files or []
	lang_code, lang_label = normalize_language(meta.get("language"))
	year = parse_year(meta.get("date") or meta.get("year"))
	file_names = {f.get("name", "") for f in files}
	has_searchtext = f"{identifier}_hocr_searchtext.txt.gz" in file_names
	has_djvu = any(n.endswith("_djvu.txt") for n in file_names)
	restricted = is_restricted(meta)

	creators = as_list(meta.get("creator"))
	alt_creators = as_list(meta.get("alt_creator"))
	page_count = meta.get("imagecount")
	try:
		page_count = int(page_count) if page_count else 0
	except (TypeError, ValueError):
		page_count = 0

	return {
		"item_id": identifier,
		"source": "Internet Archive",
		"item_type": guess_item_type(meta),
		"title": clean_text(first(meta.get("title"))) or identifier,
		"alt_title": clean_text(first(meta.get("alt_title"))),
		"creators": creators,
		"alt_creators": alt_creators,
		"date_raw": first(meta.get("date")),
		"year": year,
		"language": lang_code,
		"language_label": lang_label,
		"publisher": first(meta.get("publisher")),
		"place": first(meta.get("place") or meta.get("publisher-place")),
		"subjects": as_list(meta.get("subject")),
		"series": first(meta.get("volume") or meta.get("series")),
		"description": clean_text(" ".join(as_list(meta.get("description")))),
		"collections": public_collections(meta.get("collection")),
		"licence_url": first(meta.get("licenseurl")),
		"rights": clean_text(first(meta.get("rights"))),
		"access_status": "Restricted" if restricted else "Open",
		"page_count": page_count,
		"has_fulltext": bool((has_searchtext or has_djvu) and not restricted),
		"has_page_text": bool(has_searchtext and not restricted),
		"ark": first(meta.get("identifier-ark")),
		"isbn": first(meta.get("isbn")),
		"ocr_engine": first(meta.get("ocr")),
		"ocr_language": first(meta.get("ocr_detected_lang")),
		"scanning_centre": first(meta.get("scanningcenter")),
		"added_on_source": first(meta.get("addeddate") or meta.get("publicdate")),
		"source_url": f"https://archive.org/details/{identifier}",
		"thumbnail_url": f"https://archive.org/services/img/{identifier}",
	}


# ISO 639-3 (the catalogue's codes) → BCP 47 language tags, the shortest form browsers and screen
# readers know (W3C: use the two-letter ISO 639-1 code where there is one). Without the right
# tag a screen reader reads Kannada with an English voice, or not at all.
BCP47 = {
	"eng": "en",
	"kan": "kn",
	"hin": "hi",
	"kok": "kok",
	"ory": "or",
	"ori": "or",
	"tam": "ta",
	"mal": "ml",
	"tel": "te",
	"san": "sa",
	"mar": "mr",
	"ben": "bn",
	"guj": "gu",
	"pan": "pa",
	"urd": "ur",
	"tcy": "tcy",
	"kfa": "kfa",
	"asm": "as",
	"nep": "ne",
	"pli": "pi",
	"pra": "pra",
	"ara": "ar",
	"per": "fa",
	"fas": "fa",
	"fre": "fr",
	"fra": "fr",
	"ger": "de",
	"deu": "de",
	"por": "pt",
	"lat": "la",
	"rus": "ru",
	"spa": "es",
	"jpn": "ja",
	"chi": "zh",
	"zho": "zh",
}


def lang_tag(code: str | None) -> str:
	"""The HTML `lang` value for a catalogue language: 'kan' → 'kn'. Empty for none, several
	('mul') or unknown, so the text takes the page's language rather than a wrong one."""
	code = (code or "").strip().lower()
	if not code or code in ("mul", "und", "zxx"):
		return ""
	if len(code) == 2:
		return code
	return BCP47.get(code, "")


# first code point of each Indic script → the language its text is usually in, and which
# languages are written in it (Konkani, Tulu and Kodava books here are in Kannada script)
SCRIPT_BLOCKS = {
	0x0900: ("hi", {"hi", "mr", "sa", "ne", "kok", "pi", "pra"}),
	0x0980: ("bn", {"bn", "as"}),
	0x0A00: ("pa", {"pa"}),
	0x0A80: ("gu", {"gu"}),
	0x0B00: ("or", {"or"}),
	0x0B80: ("ta", {"ta"}),
	0x0C00: ("te", {"te"}),
	0x0C80: ("kn", {"kn", "kok", "tcy", "kfa", "sa"}),
	0x0D00: ("ml", {"ml"}),
}


def text_lang(text: str | None, code: str | None = None) -> str:
	"""The lang for a piece of text (a title, a quote) in a book catalogued as `code`: the book's
	language when the text is written in its script, else the usual language of the script the
	text is in (a Kannada title in an 'English' record), else '' (Latin letters: the page's)."""
	tag = lang_tag(code)
	for ch in text or "":
		block = ord(ch) & ~0x7F
		if block in SCRIPT_BLOCKS:
			usual, langs = SCRIPT_BLOCKS[block]
			return tag if tag in langs else usual
	return ""
