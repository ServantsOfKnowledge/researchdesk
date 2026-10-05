"""The cataloguer's review queue: records that need a person's eye. Pure Python.

Each check looks at one catalogue record (or, for duplicates, at all of them) and says what is
wrong in words a cataloguer can act on. The checks are cautious: a flag is a question, not a
verdict, and a cataloguer can answer "this is right" (ignore) once for good.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

# code -> (what the queue calls it, how much it matters: 1 most)
CHECKS = {
	"no_year": ("No year", 2),
	"odd_year": ("Year looks wrong", 1),
	"no_language": ("Language unknown", 2),
	"language_script": ("Language doesn't match the title's script", 1),
	"no_creator": ("No author", 3),
	"odd_creator": ("Author looks wrong", 2),
	"odd_title": ("Title looks wrong", 1),
	"no_subjects": ("No subjects", 4),
	"duplicate": ("Possible duplicate", 1),
}
UNKNOWN_LANGUAGES = {"", "und", "mul", "zxx", "mis"}
NOT_A_NAME = re.compile(
	r"^(unknown|anonymous|anon\.?|n/?a|none|various|na|nil|-+|\?+|author|editor|\d+)$", re.I
)
FILE_LIKE = re.compile(r"(\.(pdf|djvu|tiff?|jpe?g|zip)$|^[\w-]*_[\w-]*_[\w_-]+$|^\d{3,}[._]\d{3,})", re.I)
# Unicode block → the catalogue languages written in it (a Kannada-script title in a book
# catalogued as English is probably miscatalogued; Sanskrit and Konkani share scripts)
SCRIPTS = {
	0x0900: {"hin", "mar", "san", "nep", "kok", "pli", "pra", "awa", "bho", "mai", "new"},
	0x0980: {"ben", "asm", "san"},
	0x0A00: {"pan"},
	0x0A80: {"guj", "san"},
	0x0B00: {"ori", "san"},
	0x0B80: {"tam", "san"},
	0x0C00: {"tel", "san"},
	0x0C80: {"kan", "kok", "tcy", "kfa", "san", "sa"},
	0x0D00: {"mal", "san"},
	0x0600: {"urd", "ara", "fas", "per", "snd", "kas"},
}


def flag(code: str, detail: str = "") -> dict:
	label, weight = CHECKS[code]
	return {"code": code, "label": label, "weight": weight, "detail": detail}


def script_block(text: str) -> int | None:
	"""The Indic or Arabic block most of the title's letters are in (None: Latin or mixed)."""
	counts: dict[int, int] = {}
	letters = 0
	for ch in text or "":
		# vowel signs and other marks are part of Indic letters (ರಾ is ರ and ಾ)
		if not (ch.isalpha() or unicodedata.category(ch).startswith("M")):
			continue
		letters += 1
		block = ord(ch) & ~0x7F
		if block in SCRIPTS:
			counts[block] = counts.get(block, 0) + 1
	if not counts or not letters:
		return None
	block, n = max(counts.items(), key=lambda kv: kv[1])
	return block if n >= letters * 0.6 else None


def check(record: dict, this_year: int | None = None) -> list[dict]:
	"""What to look at in one record: {item_id, title, year, language, creators, subjects…}."""
	this_year = this_year or date.today().year
	out = []
	title = (record.get("title") or "").strip()
	year = record.get("year")
	if not year:
		raw = (record.get("date_raw") or "").strip()
		out.append(flag("no_year", f"the record says “{raw}”" if raw else ""))
	elif not (1450 <= int(year) <= this_year):
		out.append(flag("odd_year", str(year)))
	lang = (record.get("language") or "").strip().lower()
	if lang in UNKNOWN_LANGUAGES:
		out.append(flag("no_language", lang))
	else:
		block = script_block(title)
		if block and lang not in SCRIPTS[block]:
			out.append(
				flag(
					"language_script",
					f"{record.get('language_label') or lang}; the title is in another script",
				)
			)
	creators = [c for c in record.get("creators") or [] if (c or "").strip()]
	if not creators:
		out.append(flag("no_creator"))
	else:
		odd = [c for c in creators if NOT_A_NAME.match(c.strip()) or len(c) > 150]
		if odd:
			out.append(flag("odd_creator", "; ".join(o[:60] for o in odd)))
	if not title or title == record.get("item_id") or FILE_LIKE.search(title) or len(title) > 400:
		out.append(
			flag("odd_title", "same as the identifier" if title == record.get("item_id") else title[:80])
		)
	elif title.isupper() and len(title) > 12 and title.isascii():
		out.append(flag("odd_title", "all in capitals"))
	if not record.get("subjects"):
		out.append(flag("no_subjects"))
	return out


def title_key(title: str) -> str:
	"""A title for spotting duplicates: lower case, no accents, punctuation or leading article."""
	t = unicodedata.normalize("NFKD", title or "")
	t = "".join(ch for ch in t if not (unicodedata.combining(ch) and ord(ch) < 0x0900))
	t = re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFC", t).lower())
	words = t.split()
	if words and words[0] in ("the", "a", "an"):
		words = words[1:]
	return " ".join(words)


def duplicates(records: list[dict]) -> dict[str, list[str]]:
	"""{item_id: [the other items it may duplicate]}: the same title (as compared above), the same
	first author and the same year (or one of them without a year)."""
	groups: dict[tuple, list[dict]] = {}
	for r in records:
		key = title_key(r.get("title") or "")
		if len(key) < 4:
			continue
		first = title_key((r.get("creators") or [""])[0])
		groups.setdefault((key, first), []).append(r)
	out: dict[str, list[str]] = {}
	for group in groups.values():
		if len(group) < 2:
			continue
		for r in group:
			same = [
				o["item_id"]
				for o in group
				if o["item_id"] != r["item_id"]
				and (not o.get("year") or not r.get("year") or o.get("year") == r.get("year"))
			]
			if same:
				out[r["item_id"]] = same
	return out
