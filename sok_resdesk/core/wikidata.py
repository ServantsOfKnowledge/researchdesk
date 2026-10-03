"""Wikidata: naming the people, places, works and ideas a page is about. Pure Python.

A reader's note can say what its passage is about by pointing at a Wikidata item (Q-number).
That turns notes into data: every public note about Purandara Dasa (Q2724213) lists its book and
page on the portal's page for him, other tools read the link in the note's W3C form, and the
book is found by searching for his name.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

API = "https://www.wikidata.org/w/api.php"
BARE = re.compile(r"[Qq][1-9]\d{0,11}")
IN_URL = re.compile(r"/(Q[1-9]\d{0,11})(?:$|[/?#&])")


def qid(value) -> str | None:
	"""'Q42', 'q42', 'wd:Q42', 'https://www.wikidata.org/wiki/Q42',
	'http://www.wikidata.org/entity/Q42' → 'Q42'; anything else → None."""
	text = str(value or "").strip()
	if text.lower().startswith("wd:"):
		text = text[3:]
	if BARE.fullmatch(text):
		return text.upper()
	if "wikidata.org/" in text:
		m = IN_URL.search(text)
		return m.group(1) if m else None
	return None


def entity_uri(q: str) -> str:
	"""The item's identifier, as linked data uses it."""
	return f"http://www.wikidata.org/entity/{q}"


def page_url(q: str) -> str:
	"""The item's page, for people."""
	return f"https://www.wikidata.org/wiki/{q}"


def search_url(text: str, language: str = "en", limit: int = 7) -> str:
	"""Wikidata's own search-as-you-type (wbsearchentities) for `text`."""
	return (
		API
		+ "?"
		+ urlencode(
			{
				"action": "wbsearchentities",
				"search": text[:100],
				"language": language or "en",
				"uselang": language or "en",
				"type": "item",
				"limit": max(1, min(int(limit), 20)),
				"format": "json",
				"origin": "*",
			}
		)
	)


def entities_url(ids: list[str], language: str = "en") -> str:
	return (
		API
		+ "?"
		+ urlencode(
			{
				"action": "wbgetentities",
				"ids": "|".join(ids[:50]),
				"props": "labels|descriptions",
				"languages": f"{language}|en" if language and language != "en" else "en",
				"format": "json",
			}
		)
	)


def parse_search(data: dict) -> list[dict]:
	"""wbsearchentities' answer → [{id, label, description}]."""
	out = []
	for hit in (data or {}).get("search") or []:
		q = qid(hit.get("id"))
		if q:
			out.append(
				{
					"id": q,
					"label": (hit.get("label") or hit.get("display", {}).get("label", {}).get("value") or q)[
						:140
					],
					"description": (hit.get("description") or "")[:140],
				}
			)
	return out


def parse_entities(data: dict, language: str = "en") -> dict[str, dict]:
	"""wbgetentities' answer → {Q: {label, description}} in `language`, else English."""
	out = {}
	for q, ent in ((data or {}).get("entities") or {}).items():
		if "missing" in ent:
			continue

		def pick(kind: str, ent=ent) -> str:
			values = ent.get(kind) or {}
			for lang in (language, "en"):
				if lang in values:
					return values[lang].get("value") or ""
			return next(iter(values.values()), {}).get("value", "") if values else ""

		out[q] = {"label": pick("labels")[:140], "description": pick("descriptions")[:140]}
	return out


SCRIPT_LANGUAGE = {
	# first code point of each Indic block → the Wikidata language its labels are kept in
	0x0900: "hi",
	0x0980: "bn",
	0x0A00: "pa",
	0x0A80: "gu",
	0x0B00: "or",
	0x0B80: "ta",
	0x0C00: "te",
	0x0C80: "kn",
	0x0D00: "ml",
}


def search_language(text: str, default: str = "en") -> str:
	"""The language to search Wikidata's labels in: the script the words are typed in
	(ಪುರಂದರ → kn), else `default`."""
	for ch in text or "":
		block = ord(ch) & ~0x7F
		if block in SCRIPT_LANGUAGE:
			return SCRIPT_LANGUAGE[block]
	return default or "en"
