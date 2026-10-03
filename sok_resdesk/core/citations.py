"""Citation output for catalogue records.

Formats: BibTeX, BibLaTeX, RIS, CSL-JSON, and formatted APA 7 / MLA 9 /
Chicago 17 (notes-bibliography) strings. Input is a plain dict shaped like
RD Item (see `normalize.normalize_ia_item`), so this module has no Frappe
dependency and is fully unit-tested.

For non-Latin titles and names (Kannada, Hindi, ...), the original script is
kept and the romanised form (IA `alt_title` / `alt_creator`) is added in
square brackets, which is how most style guides ask for it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date

FORMATS = {
	"bibtex": ("BibTeX", "application/x-bibtex", "bib"),
	"biblatex": ("BibLaTeX", "application/x-bibtex", "bib"),
	"ris": ("RIS (Zotero, Mendeley, EndNote)", "application/x-research-info-systems", "ris"),
	"csl-json": ("CSL-JSON", "application/vnd.citationstyles.csl+json", "json"),
	"apa": ("APA 7th", "text/plain", "txt"),
	"mla": ("MLA 9th", "text/plain", "txt"),
	"chicago": ("Chicago 17th", "text/plain", "txt"),
}


# Honorifics common in Indian bibliographic data; dropped from the name when citing.
HONORIFICS = re.compile(
	r"^(?:(?:sri|shri|shree|sree|smt|srimati|shrimati|kumari|dr|prof|pandit|pt|mahamahopadhyaya|rao bahadur)\.?\s+)+",
	re.IGNORECASE,
)


# -- helpers -------------------------------------------------------------------


def _is_latin(text: str) -> bool:
	letters = [c for c in text if c.isalpha()]
	if not letters:
		return True
	return all("LATIN" in unicodedata.name(c, "") for c in letters)


def _ascii(text: str) -> str:
	return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def split_name(name: str) -> tuple[str, str]:
	"""Return (family, given). Handles "Family, Given" and "Given Family".

	Indic names do not always have a family name; for single-token names the
	whole name is treated as the family name so it still sorts and cites.
	"""
	name = re.sub(r"\s+", " ", name).strip().strip(",")
	name = HONORIFICS.sub("", name).strip()
	if not name:
		return "", ""
	if "," in name:
		family, given = name.split(",", 1)
		return family.strip(), given.strip()
	parts = name.split(" ")
	if len(parts) == 1:
		return parts[0], ""
	return parts[-1], " ".join(parts[:-1])


def _initials(given: str) -> str:
	tokens = [t for t in re.split(r"[\s.]+", given) if t]
	return " ".join(t[0] + "." for t in tokens)


def _people(item: dict) -> list[dict]:
	"""Creators with an optional romanised twin (matched by position)."""
	names = item.get("creators") or []
	alts = item.get("alt_creators") or []
	people = []
	for i, name in enumerate(names):
		alt = alts[i] if i < len(alts) else ""
		people.append({"name": name, "alt": alt if alt and alt != name else ""})
	return people


def display_title(item: dict) -> str:
	title = item.get("title") or item.get("item_id", "")
	alt = item.get("alt_title") or ""
	if alt and alt != title and not _is_latin(title):
		return f"{title} [{alt}]"
	return title


def _person_display(person: dict) -> str:
	if person["alt"] and not _is_latin(person["name"]):
		return f"{person['name']} [{person['alt']}]"
	return person["name"]


# item_type -> (BibTeX, BibLaTeX, RIS, CSL)
CITATION_TYPES = {
	"Book": ("book", "book", "BOOK", "book"),
	"Periodical": ("misc", "periodical", "JFULL", "periodical"),
	"Article": ("article", "article", "JOUR", "article-journal"),
	"Thesis": ("phdthesis", "thesis", "THES", "thesis"),
	"Report": ("techreport", "report", "RPRT", "report"),
	"Manuscript": ("unpublished", "unpublished", "MANSCPT", "manuscript"),
	"Map": ("misc", "misc", "MAP", "map"),
	"Other": ("misc", "misc", "GEN", "document"),
}


def cite_types(item: dict) -> tuple[str, str, str, str]:
	return CITATION_TYPES.get(item.get("item_type") or "Book", CITATION_TYPES["Book"])


def url_for(item: dict, base_url: str = "") -> str:
	"""The book's link for citations and records: its permanent ARK on the portal when it has
	one (it never breaks), else the portal page, else archive.org."""
	if base_url and item.get("persistent_id"):
		return f"{base_url.rstrip('/')}/{item['persistent_id']}"
	if base_url:
		return f"{base_url.rstrip('/')}/library/item/{item['item_id']}"
	return item.get("source_url") or f"https://archive.org/details/{item['item_id']}"


def cite_key(item: dict) -> str:
	people = _people(item)
	who = ""
	if people:
		name = people[0]["alt"] or people[0]["name"]
		who = _ascii(split_name(name)[0])
	title_src = item.get("alt_title") or item.get("title") or ""
	word = next((w for w in re.findall(r"[A-Za-z]{4,}", _ascii(title_src))), "")
	key = f"{who}{item.get('year') or ''}{word}".lower()
	key = re.sub(r"[^a-z0-9]", "", key)
	return key or re.sub(r"[^A-Za-z0-9_-]", "", item["item_id"])[:40]


def _bib_escape(text: str) -> str:
	return re.sub(r"([&%$#_{}])", r"\\\1", text or "")


# -- machine formats -----------------------------------------------------------


def to_bibtex(item: dict, base_url: str = "", biblatex: bool = False) -> str:
	people = _people(item)
	fields: list[tuple[str, str]] = []
	if people:
		fields.append(("author", " and ".join(_bib_escape(_person_display(p)) for p in people)))
	fields.append(("title", "{" + _bib_escape(display_title(item)) + "}"))
	if item.get("year"):
		fields.append(("date" if biblatex else "year", str(item["year"])))
	if item.get("publisher"):
		fields.append(("publisher", _bib_escape(item["publisher"])))
	if item.get("place"):
		fields.append(("location" if biblatex else "address", _bib_escape(item["place"])))
	if item.get("series"):
		fields.append(("series", _bib_escape(item["series"])))
	if item.get("language_label"):
		fields.append(("language", item["language_label"]))
	if item.get("isbn"):
		fields.append(("isbn", item["isbn"]))
	if item.get("page_count"):
		fields.append(("pagetotal", str(item["page_count"])))
	fields.append(("url", url_for(item, base_url)))
	fields.append(("urldate", date.today().isoformat()))
	if item.get("on_archive_org", True):
		note = f"Digitised by Servants of Knowledge; Internet Archive identifier {item['item_id']}"
	else:
		note = f"Digitised by Servants of Knowledge; identifier {item['item_id']}"
	if item.get("ark"):
		note += f"; {item['ark']}"
	fields.append(("note", _bib_escape(note)))
	body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
	kind = cite_types(item)[1 if biblatex else 0]
	return f"@{kind}{{{cite_key(item)},\n{body}\n}}\n"


def to_ris(item: dict, base_url: str = "") -> str:
	lines = [f"TY  - {cite_types(item)[2]}"]
	for p in _people(item):
		lines.append(f"AU  - {p['name']}")
		if p["alt"]:
			lines.append(f"A2  - {p['alt']}")
	lines.append(f"TI  - {item.get('title') or item['item_id']}")
	if item.get("alt_title") and item["alt_title"] != item.get("title"):
		lines.append(f"TT  - {item['alt_title']}")
	if item.get("year"):
		lines.append(f"PY  - {item['year']}")
	if item.get("publisher"):
		lines.append(f"PB  - {item['publisher']}")
	if item.get("place"):
		lines.append(f"CY  - {item['place']}")
	if item.get("series"):
		lines.append(f"T3  - {item['series']}")
	if item.get("language_label"):
		lines.append(f"LA  - {item['language_label']}")
	if item.get("isbn"):
		lines.append(f"SN  - {item['isbn']}")
	for s in item.get("subjects") or []:
		lines.append(f"KW  - {s}")
	if item.get("description"):
		lines.append(f"AB  - {item['description'][:2000]}")
	lines.append(f"UR  - {url_for(item, base_url)}")
	lines.append(f"Y2  - {date.today().isoformat()}")
	lines.append("DB  - Servants of Knowledge Research Desk")
	lines.append(f"AN  - {item['item_id']}")
	lines.append("ER  - ")
	return "\r\n".join(lines) + "\r\n"


def to_csl(item: dict, base_url: str = "") -> dict:
	authors = []
	for p in _people(item):
		family, given = split_name(p["name"])
		entry = {"family": family}
		if given:
			entry["given"] = given
		authors.append(entry)
	csl = {
		"id": item["item_id"],
		"type": cite_types(item)[3],
		"title": item.get("title") or item["item_id"],
		"author": authors,
		"URL": url_for(item, base_url),
		"accessed": {"date-parts": [[date.today().year, date.today().month, date.today().day]]},
		"archive": "Internet Archive",
		"archive_location": item["item_id"],
	}
	if item.get("alt_title"):
		csl["title-short"] = item["alt_title"]
	if item.get("year"):
		csl["issued"] = {"date-parts": [[item["year"]]]}
	for src, dst in (
		("publisher", "publisher"),
		("place", "publisher-place"),
		("language", "language"),
		("isbn", "ISBN"),
		("series", "collection-title"),
	):
		if item.get(src):
			csl[dst] = item[src]
	if item.get("page_count"):
		csl["number-of-pages"] = str(item["page_count"])
	return csl


# -- formatted styles ------------------------------------------------------------


def _apa_name(p: dict) -> str:
	family, given = split_name(p["alt"] or p["name"])
	return f"{family}, {_initials(given)}" if given else family


def _mla_name(p: dict, first_author: bool) -> str:
	name = p["alt"] or p["name"]
	family, given = split_name(name)
	if first_author and given:
		return f"{family}, {given}"
	return f"{given} {family}".strip()


def _join(names: list[str], conj: str = "&") -> str:
	if len(names) <= 1:
		return "".join(names)
	return ", ".join(names[:-1]) + f", {conj} " + names[-1]


def to_apa(item: dict, base_url: str = "") -> str:
	people = _people(item)
	who = _join([_apa_name(p) for p in people]) if people else ""
	year = f"({item['year']})" if item.get("year") else "(n.d.)"
	title = display_title(item)
	parts = [f"{who} {year}." if who else f"{title}. {year}."]
	if who:
		parts.append(f"{title}.")
	if item.get("publisher"):
		parts.append(f"{item['publisher']}.")
	parts.append(url_for(item, base_url))
	return " ".join(parts)


def to_mla(item: dict, base_url: str = "") -> str:
	people = _people(item)
	names = [_mla_name(p, i == 0) for i, p in enumerate(people)]
	if len(names) > 2:
		who = f"{names[0]}, et al."
	elif len(names) == 2:
		who = f"{names[0]}, and {names[1]}."
	else:
		who = f"{names[0]}." if names else ""
	parts = [who] if who else []
	parts.append(f"{display_title(item)}.")
	pub = ", ".join(str(x) for x in (item.get("publisher"), item.get("year")) if x)
	if pub:
		parts.append(f"{pub}.")
	parts.append(f"Internet Archive, {url_for(item, base_url).replace('https://', '')}.")
	return " ".join(p.replace("..", ".") for p in parts)


def to_chicago(item: dict, base_url: str = "") -> str:
	people = _people(item)
	names = [_mla_name(p, i == 0) for i, p in enumerate(people)]
	who = _join(names, "and") if names else ""
	parts = [f"{who}." if who else ""]
	parts.append(f"{display_title(item)}.")
	place_pub = ": ".join(x for x in (item.get("place"), item.get("publisher")) if x)
	tail = ", ".join(str(x) for x in (place_pub, item.get("year")) if x)
	if tail:
		parts.append(f"{tail}.")
	parts.append(f"{url_for(item, base_url)}.")
	return " ".join(p for p in parts if p).replace("..", ".")


def render(item: dict, fmt: str, base_url: str = "") -> str:
	fmt = (fmt or "bibtex").lower()
	if fmt == "bibtex":
		return to_bibtex(item, base_url)
	if fmt == "biblatex":
		return to_bibtex(item, base_url, biblatex=True)
	if fmt == "ris":
		return to_ris(item, base_url)
	if fmt in ("csl", "csl-json", "csljson"):
		return json.dumps([to_csl(item, base_url)], ensure_ascii=False, indent=2)
	if fmt == "apa":
		return to_apa(item, base_url)
	if fmt == "mla":
		return to_mla(item, base_url)
	if fmt == "chicago":
		return to_chicago(item, base_url)
	raise ValueError(f"Unknown citation format: {fmt}")


def highwire_tags(item: dict, base_url: str = "") -> list[tuple[str, str]]:
	"""<meta name=citation_*> tags read by Zotero and Google Scholar."""
	tags = [("citation_title", item.get("title") or item["item_id"])]
	for p in _people(item):
		tags.append(("citation_author", p["name"]))
	if item.get("year"):
		tags.append(("citation_publication_date", str(item["year"])))
	if item.get("publisher"):
		tags.append(("citation_publisher", item["publisher"]))
	if item.get("language"):
		tags.append(("citation_language", item["language"]))
	if item.get("isbn"):
		tags.append(("citation_isbn", item["isbn"]))
	tags.append(("citation_public_url", url_for(item, base_url)))
	if item.get("access_status") == "Open":
		pdf = item.get("pdf_url", f"https://archive.org/download/{item['item_id']}/{item['item_id']}.pdf")
		if pdf:
			tags.append(("citation_pdf_url", pdf))
	tags.append(("DC.identifier", item["item_id"]))
	return tags


def json_ld(item: dict, base_url: str = "") -> dict:
	data = {
		"@context": "https://schema.org",
		"@type": "Book",
		"@id": url_for(item, base_url),
		"name": item.get("title") or item["item_id"],
		"url": url_for(item, base_url),
		"author": [{"@type": "Person", "name": p["name"]} for p in _people(item)],
		"sameAs": item.get("source_url"),
		"isAccessibleForFree": item.get("access_status") == "Open",
	}
	if item.get("alt_title"):
		data["alternateName"] = item["alt_title"]
	if item.get("year"):
		data["datePublished"] = str(item["year"])
	if item.get("publisher"):
		data["publisher"] = {"@type": "Organization", "name": item["publisher"]}
	if item.get("language"):
		data["inLanguage"] = item["language"]
	if item.get("page_count"):
		data["numberOfPages"] = item["page_count"]
	if item.get("subjects"):
		data["keywords"] = item["subjects"]
	if item.get("licence_url"):
		data["license"] = item["licence_url"]
	if item.get("thumbnail_url"):
		data["image"] = item["thumbnail_url"]
	return data


def coins(item: dict, base_url: str = "") -> str:
	"""OpenURL COinS span title attribute (Zotero's oldest detector)."""
	from urllib.parse import urlencode

	pairs = [
		("ctx_ver", "Z39.88-2004"),
		("rft_val_fmt", "info:ofi/fmt:kev:mtx:book"),
		("rft.genre", "book"),
		("rft.btitle", item.get("title") or ""),
		("rft_id", url_for(item, base_url)),
	]
	for p in _people(item):
		pairs.append(("rft.au", p["name"]))
	if item.get("year"):
		pairs.append(("rft.date", str(item["year"])))
	if item.get("publisher"):
		pairs.append(("rft.pub", item["publisher"]))
	if item.get("isbn"):
		pairs.append(("rft.isbn", item["isbn"]))
	return urlencode(pairs)
