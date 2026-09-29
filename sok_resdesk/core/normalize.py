"""Metadata normalisation for Internet Archive records.

Pure Python (no Frappe imports) so it can be unit-tested and reused by other
sources. IA metadata is messy: languages come as "Kan", "kan", "Kannada",
"KAN"; dates default to "YYYY-01-01"; creators are strings or lists, sometimes
joined with ";". Everything that reaches the catalogue passes through here.
"""

from __future__ import annotations

import re
from typing import Any

# ISO 639-3 code -> English label. Covers what appears in SoK and common Indic
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
	"en": "eng", "english": "eng",
	"kn": "kan", "kannada": "kan", "kanada": "kan",
	"hi": "hin", "hindi": "hin",
	"konkani": "kok",
	"or": "ory", "ori": "ory", "oriya": "ory", "odia": "ory",
	"ta": "tam", "tamil": "tam",
	"ml": "mal", "malayalam": "mal",
	"te": "tel", "telugu": "tel",
	"sa": "san", "sanskrit": "san",
	"mr": "mar", "marathi": "mar",
	"bn": "ben", "bengali": "ben", "bangla": "ben",
	"gu": "guj", "gujarati": "guj",
	"pa": "pan", "punjabi": "pan",
	"ur": "urd", "urdu": "urd",
	"tulu": "tcy",
	"kodava": "kfa", "coorgi": "kfa",
	"as": "asm", "assamese": "asm",
	"ne": "nep", "nepali": "nep",
	"pali": "pli",
	"ar": "ara", "arabic": "ara",
	"fa": "per", "fas": "per", "persian": "per",
	"fr": "fre", "fra": "fre", "french": "fre",
	"de": "ger", "deu": "ger", "german": "ger",
	"pt": "por", "portuguese": "por",
	"la": "lat", "latin": "lat",
	"ru": "rus", "russian": "rus",
	"es": "spa", "spanish": "spa",
	"ja": "jpn", "japanese": "jpn",
	"zh": "chi", "zho": "chi", "chinese": "chi",
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
