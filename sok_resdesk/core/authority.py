"""Authority control: matching the catalogue's authors to Wikidata (and through it VIAF) and its
subjects to the Library of Congress Subject Headings. Pure Python.

A name in the catalogue is a string ("Kanakadasa", "Rao, B. Venkoba", "ಕುವೆಂಪು"); an authority
is a person or heading with an identifier other libraries share. Matching them lets the portal
gather a writer's books under one name whatever spelling a record used, link to what is known
about them, and send the identifiers along in MARC, JSON-LD and the other exports.

Machines propose; people decide. Each author gets candidates with a score (how alike the names
are, whether the candidate is a person, whether their dates fit the books); a cataloguer accepts
one or none on Desk → Authorities. Only a near-certain match is accepted without a person, and
only when the library switches that on.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from urllib.parse import urlencode

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
LCSH_SUGGEST = "https://id.loc.gov/authorities/subjects/suggest2"
VIAF = "https://viaf.org/viaf/"
HUMAN = "Q5"
# properties read from a Wikidata person
P_INSTANCE, P_BIRTH, P_DEATH, P_VIAF = "P31", "P569", "P570", "P214"
LABEL_LANGUAGES = ("en", "kn", "hi", "sa", "ta", "te", "ml", "mr", "bn", "gu", "pa", "or", "gom", "ne", "tcy")

# titles and words that are not part of the name ("Sri", "Dr.", "Pandit", "Late"…)
HONORIFICS = {
	"sri",
	"shri",
	"shree",
	"sree",
	"srimati",
	"smt",
	"dr",
	"prof",
	"pandit",
	"pt",
	"mr",
	"mrs",
	"ms",
	"late",
	"swami",
	"acharya",
	"mahamahopadhyaya",
	"rao bahadur",
	"sir",
	"ed",
	"eds",
	"editor",
	"tr",
	"trans",
	"comp",
	"ಶ್ರೀ",
	"ಡಾ",
	"श्री",
	"डॉ",
}
_DATES = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\s*-\s*(1[0-9]{3}|20[0-9]{2})?\b")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _fold(text: str) -> str:
	"""Lower case without accents (Rāmānuja → ramanuja); Indic letters are kept as they are."""
	out = []
	for ch in unicodedata.normalize("NFKD", text or ""):
		if unicodedata.combining(ch) and ord(ch) < 0x0900:
			continue  # a Latin accent; Indic vowel signs are combining too, and are kept
		out.append(ch)
	return unicodedata.normalize("NFC", "".join(out)).lower()


def name_dates(name: str) -> tuple[str, int | None, int | None]:
	"""'Rao, B. Venkoba, 1890-1960' → ('Rao, B. Venkoba', 1890, 1960)."""
	m = _DATES.search(name or "")
	if not m:
		return (name or "").strip(" ,"), None, None
	clean = (name[: m.start()] + name[m.end() :]).strip(" ,;")
	return clean, int(m.group(1)), int(m.group(2)) if m.group(2) else None


def name_key(name: str) -> str:
	"""A name for comparing: in reading order ("Rao, B. Venkoba" → "b venkoba rao"), without
	titles, dates, punctuation or accents."""
	name, _b, _d = name_dates(name)
	if name.count(",") == 1:
		family, given = (p.strip() for p in name.split(","))
		if family and given:
			name = f"{given} {family}"
	words = [w for w in _PUNCT.sub(" ", _fold(name)).split() if w not in HONORIFICS]
	return " ".join(words)


def name_similarity(a: str, b: str) -> float:
	"""0–1: how alike two names are, whatever their order or initials ("B. Venkoba Rao" and
	"Venkoba Rao B" are alike; "Rao" alone is only partly)."""
	ka, kb = name_key(a), name_key(b)
	if not ka or not kb:
		return 0.0
	if ka == kb:
		return 1.0
	wa, wb = ka.split(), kb.split()

	# initials match a word starting with them (b ↔ bhimasena)
	def covered(x: list[str], y: list[str]) -> float:
		hits = 0
		for w in x:
			if w in y or (len(w) == 1 and any(v.startswith(w) for v in y)):
				hits += 1
			elif any(len(v) == 1 and w.startswith(v) for v in y):
				hits += 0.8
		return hits / len(x)

	words = (covered(wa, wb) + covered(wb, wa)) / 2
	chars = difflib.SequenceMatcher(None, " ".join(sorted(wa)), " ".join(sorted(wb))).ratio()
	return round(max(words * 0.95, chars * 0.9), 3)


# ---- Wikidata ------------------------------------------------------------------------------------


def search_url(text: str, language: str = "en", limit: int = 10) -> str:
	return (
		WIKIDATA_API
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
			}
		)
	)


def entities_url(ids: list[str]) -> str:
	return (
		WIKIDATA_API
		+ "?"
		+ urlencode(
			{
				"action": "wbgetentities",
				"ids": "|".join(ids[:50]),
				"props": "labels|aliases|descriptions|claims",
				"languages": "|".join(LABEL_LANGUAGES),
				"format": "json",
			}
		)
	)


def _year(claim: dict) -> int | None:
	try:
		time = claim["mainsnak"]["datavalue"]["value"]["time"]  # "+1509-00-00T00:00:00Z"
		year = int(time[1:5]) if time[0] == "+" else -int(time[1:5])
		return year
	except (KeyError, TypeError, ValueError, IndexError):
		return None


def _ids(claims: list[dict]) -> list[str]:
	out = []
	for c in claims or []:
		v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
		if isinstance(v, dict) and v.get("id"):
			out.append(v["id"])
		elif isinstance(v, str):
			out.append(v)
	return out


def parse_people(data: dict) -> list[dict]:
	"""wbgetentities' answer → [{id, label, labels, aliases, description, human, born, died, viaf}]."""
	out = []
	for q, ent in ((data or {}).get("entities") or {}).items():
		if "missing" in ent:
			continue
		labels = {k: v.get("value", "") for k, v in (ent.get("labels") or {}).items()}
		descriptions = {k: v.get("value", "") for k, v in (ent.get("descriptions") or {}).items()}
		aliases = [a.get("value", "") for vs in (ent.get("aliases") or {}).values() for a in vs]
		claims = ent.get("claims") or {}
		births = [y for y in (_year(c) for c in claims.get(P_BIRTH) or []) if y is not None]
		deaths = [y for y in (_year(c) for c in claims.get(P_DEATH) or []) if y is not None]
		viaf = _ids(claims.get(P_VIAF))
		out.append(
			{
				"id": q,
				"label": labels.get("en") or next(iter(labels.values()), q),
				"labels": labels,
				"aliases": aliases[:30],
				"description": descriptions.get("en") or next(iter(descriptions.values()), ""),
				"human": HUMAN in _ids(claims.get(P_INSTANCE)),
				"born": min(births) if births else None,
				"died": min(deaths) if deaths else None,
				"viaf": viaf[0] if viaf else "",
			}
		)
	return out


def score_person(names: list[str], candidate: dict, years: list[int] | None = None) -> dict:
	"""How likely the candidate is the author: {score 0–1, reasons}. `names` are the catalogue's
	forms of the name (as given, romanised); `years` the years of the author's books."""
	forms = [
		candidate.get("label") or "",
		*candidate.get("labels", {}).values(),
		*candidate.get("aliases", []),
	]
	best = max((name_similarity(n, f) for n in names if n for f in forms if f), default=0.0)
	reasons = [f"name {int(best * 100)}%"]
	score = best
	if not candidate.get("human"):
		score *= 0.5
		reasons.append("not a person on Wikidata")
	years = sorted(y for y in (years or []) if y)
	born, died = candidate.get("born"), candidate.get("died")
	given_born = next((b for n in names for _x, b, _y in [name_dates(n)] if b), None)
	if given_born and born:
		if abs(given_born - born) <= 2:
			score = min(1.0, score + 0.1)
			reasons.append("birth year matches the catalogue's")
		else:
			score *= 0.6
			reasons.append(f"born {born}, the catalogue says {given_born}")
	if years and born:
		if years[0] < born + 12:
			score *= 0.6  # a book before the candidate was twelve
			reasons.append(f"born {born}, after the earliest book could be theirs ({years[0]})")
		else:
			reasons.append(f"born {born}")
	elif born:
		reasons.append(f"born {born}")
	if died:
		reasons.append(f"died {died}")
	if candidate.get("viaf"):
		reasons.append("has a VIAF record")
	return {"score": round(min(score, 1.0), 3), "reasons": reasons}


def rank(names: list[str], candidates: list[dict], years: list[int] | None = None) -> list[dict]:
	"""The candidates with their scores, best first."""
	out = []
	for c in candidates:
		s = score_person(names, c, years)
		out.append({**c, **s})
	return sorted(out, key=lambda c: c["score"], reverse=True)


PROPOSE_AT = 0.7  # below this, the names only look alike (Kanakadasa / Purandaradasa)


def decide(ranked: list[dict], auto_threshold: float = 0.95, margin: float = 0.15) -> str:
	"""What to do with a ranked list: "auto" (near-certain: one person, the name alike, no
	rival close behind), "propose" (someone to look at) or "none"."""
	if not ranked or ranked[0]["score"] < PROPOSE_AT:
		return "none"
	top = ranked[0]
	second = ranked[1]["score"] if len(ranked) > 1 else 0.0
	if top["score"] >= auto_threshold and top.get("human") and top["score"] - second >= margin:
		return "auto"
	return "propose"


def viaf_url(viaf_id: str) -> str:
	return f"{VIAF}{viaf_id}" if viaf_id else ""


# ---- Library of Congress Subject Headings ----------------------------------------------------------


def lcsh_url(text: str, limit: int = 8) -> str:
	return (
		LCSH_SUGGEST
		+ "?"
		+ urlencode({"q": text[:100], "searchtype": "keyword", "count": max(1, min(int(limit), 20))})
	)


def parse_lcsh(data: dict) -> list[dict]:
	"""id.loc.gov's suggest2 answer → [{id, label, uri}] (id: sh85061212)."""
	out = []
	for hit in (data or {}).get("hits") or []:
		uri = hit.get("uri") or ""
		label = hit.get("aLabel") or hit.get("suggestLabel") or ""
		if not uri or not label:
			continue
		out.append({"id": uri.rstrip("/").rsplit("/", 1)[-1], "label": label, "uri": uri})
	return out


def score_subject(name: str, candidate: dict) -> float:
	"""How alike a subject and an LCSH heading are ("History -- India" ~ "India--History")."""

	def key(s: str) -> str:
		return " ".join(sorted(_PUNCT.sub(" ", _fold(s)).split()))

	a, b = key(name), key(candidate.get("label") or "")
	if not a or not b:
		return 0.0
	return round(1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio() * 0.95, 3)
