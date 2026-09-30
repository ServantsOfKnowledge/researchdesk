"""Curated collections: slugs and inclusion rules. Pure Python, unit-tested."""

from __future__ import annotations

import re
import unicodedata

from sok_resdesk.core.access import _values

RULE_FIELDS = ("Source Collection", "Subject", "Language", "Creator", "Source", "Ingest Profile", "Document Type")
_FIELD_MAP = {"Source Collection": "Collection", "Document Type": "Item Type"}


def slugify(text: str) -> str:
	"""URL-safe id from a title; keeps non-Latin letters (ಕನ್ನಡ stays readable)."""
	text = unicodedata.normalize("NFKC", text or "").strip().lower()
	# keep letters, combining marks (Indic vowel signs) and digits; drop punctuation and symbols
	text = "".join(c if unicodedata.category(c)[0] in "LMN" or c in " -_" else " " for c in text)
	text = re.sub(r"[\s_-]+", "-", text).strip("-")
	return text[:80] or "collection"


def _field_values(record: dict, field: str) -> list[str]:
	if field == "Document Type":
		return [str(record.get("item_type") or "Book").casefold()]
	return _values(record, _FIELD_MAP.get(field, field))


def matches(record: dict, rules: list[dict]) -> bool:
	"""True if any rule matches (rules are alternatives: 'include books that are X or Y')."""
	for rule in rules or []:
		value = (rule.get("value") or "").strip().casefold()
		if not value:
			continue
		have = _field_values(record, rule.get("match_on") or "")
		if rule.get("how") == "contains":
			if any(value in h for h in have):
				return True
		elif value in have:
			return True
	return False
