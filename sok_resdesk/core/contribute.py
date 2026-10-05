"""Giving back to the authorities: what the library knows that Wikidata and the Library of
Congress don't yet. Pure Python.

Once a cataloguer has matched an author to a person on Wikidata, the library often knows things
Wikidata lacks: the person's name in the books' own script (ಕನಕದಾಸ for an item labelled only
"Kanakadasa" in English), and which editions they wrote. Research Desk turns that into edits:

* **names**: a label in a language the person has none in, otherwise an alias;
* **authors**: on the library's book items on Wikidata, "author" (P50) linked to the person,
  with the name as printed ("stated as", P1932), where the item doesn't link them yet.

Edits are proposals. They are written as QuickStatements (the batch tool Wikidata editors use:
a person reviews and runs them under their own account) or sent through the library's Wikidata
Push Target. Nothing already on Wikidata is changed or removed.

Subjects the Library of Congress headings lack are listed for SACO proposals (the programme
through which libraries propose new LCSH headings); there is no API to propose them directly.
"""

from __future__ import annotations

import csv
import io
import re

from sok_resdesk.core.authority import _fold

SCRIPT_LANGUAGE = {
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
STATED_AS, AUTHOR, ORDINAL, REF_URL = "P1932", "P50", "P1545", "S854"
_SPACE = re.compile(r"[\t\n\r]+")


def name_language(name: str, book_language: str = "") -> str | None:
	"""The Wikimedia language a name is written for: its script (ಕನಕದಾಸ → kn; Devanagari: the
	book's language if it is written in it, else hi), or None for Latin letters (romanised forms
	are already on Wikidata more often than not, and their language can't be told)."""
	for ch in name or "":
		block = ord(ch) & ~0x7F
		if block in SCRIPT_LANGUAGE:
			lang = SCRIPT_LANGUAGE[block]
			if block == 0x0900 and book_language in ("mr", "sa", "ne", "gom", "kok"):
				return "gom" if book_language == "kok" else book_language
			return lang
	return None


def _same(a: str, b: str) -> bool:
	return _fold(a).strip(" .,") == _fold(b).strip(" .,")


def name_edits(qid: str, entity: dict, names: list[tuple[str, str]]) -> list[dict]:
	"""Labels or aliases to add to a person: `entity` is what Wikidata has ({labels: {lang:
	text}, aliases: {lang: [text]}}), `names` the catalogue's forms as (name, book language)."""
	labels = dict(entity.get("labels") or {})
	aliases = {k: list(v) for k, v in (entity.get("aliases") or {}).items()}
	out = []
	for name, book_lang in names:
		name = (name or "").strip()
		lang = name_language(name, book_lang)
		if not lang or len(name) < 2:
			continue
		known = [labels.get(lang, "")] + aliases.get(lang, [])
		if any(_same(name, k) for k in known if k):
			continue
		if not labels.get(lang):
			out.append({"qid": qid, "kind": "label", "lang": lang, "value": name})
			labels[lang] = name
		else:
			out.append({"qid": qid, "kind": "alias", "lang": lang, "value": name})
			aliases.setdefault(lang, []).append(name)
	return out


def author_edits(book_qid: str, claims: dict, authors: list[dict]) -> list[dict]:
	"""P50 statements a book item lacks: `claims` is the item's claims (property → list), `authors`
	[{qid, name, ordinal}] the book's matched authors."""
	linked = {
		((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
		for c in (claims or {}).get(AUTHOR) or []
	}
	return [
		{"qid": book_qid, "kind": "author", "person": a["qid"], "value": a["name"], "ordinal": a["ordinal"]}
		for a in authors
		if a.get("qid") and a["qid"] not in linked
	]


def _q(text: str) -> str:
	# QuickStatements strings can't hold a double quote, a tab or a line break
	return '"' + _SPACE.sub(" ", (text or "").replace('"', "'")).strip() + '"'


def quickstatements(edits: list[dict], source_url: str = "") -> str:
	"""The edits as QuickStatements (version 1, tab-separated), one per line. Statements carry
	the library's portal as their reference."""
	lines = []
	for e in edits:
		if e["kind"] == "label":
			lines.append(f"{e['qid']}\tL{e['lang']}\t{_q(e['value'])}")
		elif e["kind"] == "alias":
			lines.append(f"{e['qid']}\tA{e['lang']}\t{_q(e['value'])}")
		elif e["kind"] == "author":
			line = f"{e['qid']}\t{AUTHOR}\t{e['person']}\t{STATED_AS}\t{_q(e['value'])}\t{ORDINAL}\t{_q(str(e['ordinal']))}"
			url = e.get("source_url") or source_url
			if url:
				line += f"\t{REF_URL}\t{_q(url)}"
			lines.append(line)
	return "\n".join(lines) + ("\n" if lines else "")


def wbeditentity_data(edits: list[dict]) -> dict:
	"""The edits for one item as wbeditentity data (labels, aliases added, claims)."""
	data: dict = {}
	for e in edits:
		if e["kind"] == "label":
			data.setdefault("labels", {})[e["lang"]] = {"language": e["lang"], "value": e["value"]}
		elif e["kind"] == "alias":
			data.setdefault("aliases", []).append({"language": e["lang"], "value": e["value"], "add": ""})
		elif e["kind"] == "author":
			claim = {
				"mainsnak": {
					"snaktype": "value",
					"property": AUTHOR,
					"datavalue": {
						"value": {
							"entity-type": "item",
							"numeric-id": int(e["person"][1:]),
							"id": e["person"],
						},
						"type": "wikibase-entityid",
					},
				},
				"type": "statement",
				"rank": "normal",
				"qualifiers": {
					STATED_AS: [
						{
							"snaktype": "value",
							"property": STATED_AS,
							"datavalue": {"value": e["value"], "type": "string"},
						}
					],
					ORDINAL: [
						{
							"snaktype": "value",
							"property": ORDINAL,
							"datavalue": {"value": str(e["ordinal"]), "type": "string"},
						}
					],
				},
			}
			if e.get("source_url"):
				claim["references"] = [
					{
						"snaks": {
							"P854": [
								{
									"snaktype": "value",
									"property": "P854",
									"datavalue": {"value": e["source_url"], "type": "string"},
								}
							]
						}
					}
				]
			data.setdefault("claims", []).append(claim)
	return data


def saco_csv(rows: list[dict]) -> str:
	"""Subjects without an LCSH heading, for SACO proposals: the heading as the catalogue has it,
	how many books, example titles, and the portal's search for them."""
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(["subject", "books", "example titles", "portal search", "candidates looked at"])
	for r in rows:
		w.writerow(
			[
				r["subject"],
				r["books"],
				" | ".join(r.get("titles") or []),
				r.get("url", ""),
				r.get("looked_at", ""),
			]
		)
	return buf.getvalue()
