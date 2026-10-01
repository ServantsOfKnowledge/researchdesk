"""MARC21 (MARCXML) records for Koha and other library systems.

Koha's "Stage MARC records for import" accepts MARCXML directly, so we do not
need a binary ISO 2709 writer. Records carry an 856 link back to the portal and
the Internet Archive so the library catalogue points at the digital copy.
"""

from __future__ import annotations

from datetime import datetime
from xml.sax.saxutils import escape

from .citations import split_name, url_for

MARC_NS = "http://www.loc.gov/MARC21/slim"

# MARC language codes (MARC Code List for Languages) differ from ISO 639-3 for a few
_MARC_LANG = {"ory": "ori", "fre": "fre", "ger": "ger", "per": "per", "tcy": "tcy"}


def _sf(code: str, value) -> str:
	return f'<subfield code="{code}">{escape(str(value))}</subfield>'


def _df(tag: str, ind1: str, ind2: str, *subfields: str) -> str:
	inner = "".join(s for s in subfields if s)
	if not inner:
		return ""
	return f'<datafield tag="{tag}" ind1="{ind1}" ind2="{ind2}">{inner}</datafield>'


def _cf(tag: str, value: str) -> str:
	return f'<controlfield tag="{tag}">{escape(value)}</controlfield>'


def _heading(name: str) -> str:
	family, given = split_name(name)
	return f"{family}, {given}" if given else family


def fixed_008(item: dict) -> str:
	entered = datetime.now().strftime("%y%m%d")
	year = str(item.get("year") or "    ")
	date_type = "s" if item.get("year") else "n"
	code = item.get("language") or ""
	lang = _MARC_LANG.get(code, code) if len(code) == 3 else "und"
	# 008 for books, position by position (40 chars). 23 = form of item "o" (online).
	value = (
		entered  # 00-05 date entered
		+ date_type  # 06 type of date
		+ f"{year:<4}"  # 07-10 date 1
		+ "    "  # 11-14 date 2
		+ "ii "  # 15-17 place of publication (India)
		+ "    "  # 18-21 illustrations
		+ " "  # 22 audience
		+ "o"  # 23 form of item
		+ "    "  # 24-27 nature of contents
		+ "0"  # 28 government publication
		+ "0"  # 29 conference
		+ "0"  # 30 festschrift
		+ "0"  # 31 index
		+ " "  # 32 undefined
		+ "0"  # 33 literary form (unknown -> not fiction)
		+ " "  # 34 biography
		+ lang  # 35-37 language
		+ " "  # 38 modified record
		+ "d"  # 39 cataloguing source (other)
	)
	assert len(value) == 40, value
	return value


def to_marcxml_record(item: dict, base_url: str = "", with_namespace: bool = False) -> str:
	creators = item.get("creators") or []
	alt_creators = item.get("alt_creators") or []
	fields = [
		f"<leader>{'00000nam a22000007i 4500'}</leader>",
		_cf("001", item["item_id"]),
		_cf("003", "SOK-ResDesk"),
		_cf("005", datetime.now().strftime("%Y%m%d%H%M%S.0")),
		_cf("007", "cr |||||||||||"),
		_cf("008", fixed_008(item)),
	]
	if item.get("isbn"):
		fields.append(_df("020", " ", " ", _sf("a", item["isbn"])))
	fields.append(_df("035", " ", " ", _sf("a", f"(IA){item['item_id']}")))
	if item.get("language"):
		fields.append(_df("041", "0", " ", _sf("a", item["language"])))
	if creators:
		fields.append(_df("100", "1", " ", _sf("a", _heading(creators[0])), _sf("e", "author")))
	title = item.get("title") or item["item_id"]
	fields.append(_df("245", "1" if creators else "0", "0", _sf("a", title)))
	if item.get("alt_title") and item["alt_title"] != title:
		fields.append(_df("246", "3", "1", _sf("a", item["alt_title"])))
	pub = [
		_sf("a", item["place"]) if item.get("place") else "",
		_sf("b", item["publisher"]) if item.get("publisher") else "",
		_sf("c", item["year"]) if item.get("year") else "",
	]
	fields.append(_df("264", " ", "1", *pub))
	if item.get("page_count"):
		fields.append(_df("300", " ", " ", _sf("a", f"1 online resource ({item['page_count']} pages)")))
	fields.append(_df("336", " ", " ", _sf("a", "text"), _sf("b", "txt"), _sf("2", "rdacontent")))
	fields.append(_df("337", " ", " ", _sf("a", "computer"), _sf("b", "c"), _sf("2", "rdamedia")))
	fields.append(_df("338", " ", " ", _sf("a", "online resource"), _sf("b", "cr"), _sf("2", "rdacarrier")))
	if item.get("series"):
		fields.append(_df("490", "0", " ", _sf("a", item["series"])))
	if item.get("description"):
		fields.append(_df("520", " ", " ", _sf("a", item["description"][:4000])))
	if item.get("licence_url") or item.get("rights"):
		fields.append(
			_df(
				"540",
				" ",
				" ",
				_sf("a", item.get("rights") or "See licence"),
				_sf("u", item["licence_url"]) if item.get("licence_url") else "",
			)
		)
	fields.append(
		_df(
			"533",
			" ",
			" ",
			_sf("a", "Electronic reproduction."),
			_sf("b", "Bengaluru :"),
			_sf("c", "Servants of Knowledge / Internet Archive."),
		)
	)
	for s in item.get("subjects") or []:
		fields.append(_df("653", " ", " ", _sf("a", s)))
	for name in creators[1:]:
		fields.append(_df("700", "1", " ", _sf("a", _heading(name))))
	for alt in alt_creators:
		if alt not in creators:
			fields.append(_df("700", "1", " ", _sf("a", _heading(alt)), _sf("e", "romanized form")))
	fields.append(
		_df("856", "4", "0", _sf("u", url_for(item, base_url)), _sf("y", "Read online (Research Desk)"))
	)
	if item.get("source_url"):
		fields.append(_df("856", "4", "1", _sf("u", item["source_url"]), _sf("y", "Internet Archive")))
	ns = f' xmlns="{MARC_NS}"' if with_namespace else ""
	return f"<record{ns}>" + "".join(f for f in fields if f) + "</record>"


def to_marcxml_collection(items: list[dict], base_url: str = "") -> str:
	body = "".join(to_marcxml_record(i, base_url) for i in items)
	return f'<?xml version="1.0" encoding="UTF-8"?>\n<collection xmlns="{MARC_NS}">{body}</collection>\n'
