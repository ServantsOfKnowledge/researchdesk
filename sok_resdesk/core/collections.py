"""Curated collections: slugs and inclusion rules. Pure Python, unit-tested."""

from __future__ import annotations

import re
import unicodedata

from sok_resdesk.core.access import _values

RULE_FIELDS = (
	"Source Collection",
	"Subject",
	"Language",
	"Creator",
	"Source",
	"Ingest Profile",
	"Document Type",
)
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


def group_tree(cards: list[dict]) -> dict:
	"""Collections for one page that shows them all: {"groups": [{"parent", "children"}],
	"single": [...]}. Each top-level collection with sub-collections is a group, its
	descendants listed under it in order (depth-first, each with its `depth` and `trail` of
	parent titles); top-level collections without any are listed together. Cards keep the order
	they come in (sort order, then title)."""
	by_parent: dict[str | None, list[dict]] = {}
	names = {c["name"] for c in cards}
	for c in cards:
		parent = c.get("part_of") if c.get("part_of") in names else None
		by_parent.setdefault(parent, []).append(c)

	def descend(name: str, depth: int, trail: list[str], seen: set[str]) -> list[dict]:
		out = []
		for child in by_parent.get(name, []):
			if child["name"] in seen:  # a loop in part_of: show each collection once
				continue
			seen.add(child["name"])
			out.append({**child, "depth": depth, "trail": trail})
			out.extend(descend(child["name"], depth + 1, [*trail, child.get("title") or child["name"]], seen))
		return out

	groups, single = [], []
	for top in by_parent.get(None, []):
		children = descend(top["name"], 1, [], {top["name"]})
		if children:
			groups.append({"parent": top, "children": children})
		else:
			single.append(top)
	return {"groups": groups, "single": single}
