"""Metadata in and out: spreadsheet rows, Dublin Core, MODS, JSON-LD, Internet Archive formats.

Pure Python (no Frappe), unit-tested in tests/test_core.py. Records are the dicts produced
by catalogue.item_to_record.
"""

from __future__ import annotations

import csv
import io
import json
from xml.sax.saxutils import escape

from sok_resdesk.core.citations import CITATION_TYPES, json_ld, url_for
from sok_resdesk.core.normalize import ITEM_TYPES

LIST_SEP = "; "

# Spreadsheet columns: (column, record key, editable)
COLUMNS = (
	("item_id", "item_id", False),
	("title", "title", True),
	("alt_title", "alt_title", True),
	("creators", "creators", True),
	("alt_creators", "alt_creators", True),
	("item_type", "item_type", True),
	("year", "year", True),
	("date", "date_raw", True),
	("publisher", "publisher", True),
	("place", "place", True),
	("language", "language", True),
	("series", "series", True),
	("isbn", "isbn", True),
	("subjects", "subjects", True),
	("collections", "curated_collections", True),
	("visibility", "visibility", True),
	("published", "published", True),
	("licence_url", "licence_url", True),
	("rights", "rights", True),
	("description", "description", True),
	("source_collections", "collections", False),
	("source", "source", False),
	("page_count", "page_count", False),
	("portal_url", "portal_url", False),
	("source_url", "source_url", False),
)
LIST_KEYS = {"creators", "alt_creators", "subjects", "curated_collections", "collections"}
EDITABLE = {col: key for col, key, editable in COLUMNS if editable}
VISIBILITIES = ("Public", "Login to read", "Login to find")


def _cell(value) -> str:
	if value is None:
		return ""
	if isinstance(value, bool):
		return "1" if value else "0"
	if isinstance(value, (list, tuple)):
		return LIST_SEP.join(str(v) for v in value if v not in (None, ""))
	return str(value)


def record_to_row(record: dict, base_url: str = "") -> dict:
	rec = {**record, "portal_url": url_for(record, base_url) if base_url else ""}
	rec.setdefault("published", True)
	return {col: _cell(rec.get(key)) for col, key, _editable in COLUMNS}


def rows_to_csv(rows: list[dict]) -> str:
	out = io.StringIO()
	writer = csv.DictWriter(out, fieldnames=[c for c, _k, _e in COLUMNS], extrasaction="ignore")
	writer.writeheader()
	writer.writerows(rows)
	return "﻿" + out.getvalue()  # BOM so Excel opens Kannada text correctly


def csv_to_rows(data: bytes | str) -> list[dict]:
	text = data.decode("utf-8-sig") if isinstance(data, bytes) else data.lstrip("﻿")
	return [
		{(k or "").strip(): (v or "").strip() for k, v in row.items()}
		for row in csv.DictReader(io.StringIO(text))
	]


def _split(value: str) -> list[str]:
	return [v.strip() for v in value.replace("|", ";").split(";") if v.strip()]


def row_changes(row: dict, current: dict) -> tuple[dict, list[str]]:
	"""Compare one spreadsheet row with the catalogue record.

	Returns (changes, problems). Only columns present in the sheet are considered, so a sheet
	with just item_id and subjects changes only subjects. Blank cells clear a field.
	"""
	changes, problems = {}, []
	for col, key in EDITABLE.items():
		if col not in row:
			continue
		raw = row[col]
		if key in LIST_KEYS:
			value = _split(raw)
			if value != list(current.get(key) or []):
				changes[key] = value
			continue
		if key == "year":
			if raw and not raw.isdigit():
				problems.append(f"year '{raw}' is not a number")
				continue
			value = int(raw) if raw else None
		elif key == "published":
			value = raw.strip().lower() in ("1", "yes", "true", "y")
		elif key == "item_type":
			value = next((t for t in ITEM_TYPES if t.lower() == raw.lower()), None) if raw else "Book"
			if value is None:
				problems.append(f"document type '{raw}' is not one of {', '.join(ITEM_TYPES)}")
				continue
		elif key == "visibility":
			value = next((v for v in VISIBILITIES if v.lower() == raw.lower()), None) if raw else "Public"
			if value is None:
				problems.append(f"visibility '{raw}' is not one of {', '.join(VISIBILITIES)}")
				continue
		else:
			value = raw
		old = current.get(key)
		if key == "published":
			old = bool(old if old is not None else True)
		if (old if old not in (None, "") else "") != (value if value not in (None, "") else ""):
			changes[key] = value
	return changes, problems


# -- library and web formats ----------------------------------------------------------------------


def _x(tag: str, value, attrs: str = "") -> str:
	return f"<{tag}{attrs}>{escape(str(value))}</{tag}>" if value not in (None, "", []) else ""


def dublin_core(record: dict, base_url: str = "") -> str:
	parts = [_x("dc:title", record.get("title"))]
	if record.get("alt_title") and record["alt_title"] != record.get("title"):
		parts.append(_x("dc:title", record["alt_title"]))
	parts += [_x("dc:creator", c) for c in record.get("creators") or []]
	parts += [_x("dc:subject", s) for s in record.get("subjects") or []]
	parts += [
		_x("dc:description", record.get("description")),
		_x("dc:publisher", record.get("publisher")),
		_x("dc:date", record.get("date_raw") or record.get("year")),
		_x("dc:type", "Text"),
		_x("dc:type", record.get("item_type") or "Book"),
		_x("dc:format", f"{record['page_count']} pages" if record.get("page_count") else ""),
		_x("dc:identifier", url_for(record, base_url)),
		_x("dc:identifier", record.get("ark")),
		_x("dc:identifier", f"ISBN {record['isbn']}" if record.get("isbn") else ""),
		_x("dc:language", record.get("language")),
		_x("dc:relation", record.get("series")),
		_x("dc:rights", record.get("licence_url") or record.get("rights")),
		_x("dc:source", record.get("source_url")),
	]
	return (
		'<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
		'xmlns:dc="http://purl.org/dc/elements/1.1/">' + "".join(p for p in parts if p) + "</oai_dc:dc>"
	)


def dublin_core_collection(records: list[dict], base_url: str = "") -> str:
	body = "\n".join(dublin_core(r, base_url) for r in records)
	return f'<?xml version="1.0" encoding="UTF-8"?>\n<records count="{len(records)}">\n{body}\n</records>\n'


_MODS_GENRE = {
	"Book": "book",
	"Periodical": "periodical",
	"Article": "article",
	"Thesis": "thesis",
	"Report": "technical report",
	"Manuscript": "manuscript",
	"Map": "map",
	"Other": "text",
}


def mods(record: dict, base_url: str = "") -> str:
	p = []
	p.append(f"<titleInfo>{_x('title', record.get('title') or record['item_id'])}</titleInfo>")
	if record.get("alt_title") and record["alt_title"] != record.get("title"):
		p.append(f'<titleInfo type="alternative">{_x("title", record["alt_title"])}</titleInfo>')
	for c in record.get("creators") or []:
		p.append(
			f'<name type="personal">{_x("namePart", c)}<role><roleTerm type="text" authority="marcrelator">author</roleTerm></role></name>'
		)
	p.append(_x("typeOfResource", "text"))
	p.append(_x("genre", _MODS_GENRE.get(record.get("item_type") or "Book", "book"), ' authority="local"'))
	origin = "".join(
		[
			f'<place><placeTerm type="text">{escape(record["place"])}</placeTerm></place>'
			if record.get("place")
			else "",
			_x("publisher", record.get("publisher")),
			_x("dateIssued", record.get("date_raw") or record.get("year")),
		]
	)
	if origin:
		p.append(f"<originInfo>{origin}</originInfo>")
	if record.get("language"):
		p.append(
			f'<language><languageTerm type="code" authority="iso639-2b">{escape(record["language"])}</languageTerm></language>'
		)
	if record.get("page_count"):
		p.append(
			f"<physicalDescription>{_x('extent', str(record['page_count']) + ' pages')}"
			f"{_x('digitalOrigin', 'reformatted digital')}</physicalDescription>"
		)
	p.append(_x("abstract", record.get("description")))
	p += [f"<subject>{_x('topic', s)}</subject>" for s in record.get("subjects") or []]
	if record.get("series"):
		p.append(
			f'<relatedItem type="series"><titleInfo>{_x("title", record["series"])}</titleInfo></relatedItem>'
		)
	p.append(_x("identifier", record.get("isbn"), ' type="isbn"'))
	p.append(_x("identifier", record.get("ark"), ' type="ark"'))
	p.append(_x("identifier", record["item_id"], ' type="local"'))
	usage = ' usage="primary display"'
	p.append(
		"<location>"
		+ _x("url", url_for(record, base_url), usage)
		+ _x("url", record.get("source_url"))
		+ "</location>"
	)
	p.append(
		_x(
			"accessCondition",
			record.get("licence_url") or record.get("rights"),
			' type="use and reproduction"',
		)
	)
	return "<mods>" + "".join(x for x in p if x) + "</mods>"


def mods_collection(records: list[dict], base_url: str = "") -> str:
	body = "\n".join(mods(r, base_url) for r in records)
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n<modsCollection xmlns="http://www.loc.gov/mods/v3" '
		'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xsi:schemaLocation="http://www.loc.gov/mods/v3 http://www.loc.gov/standards/mods/v3/mods-3-7.xsd">\n'
		f"{body}\n</modsCollection>\n"
	)


def jsonld_graph(records: list[dict], base_url: str = "") -> str:
	graph = []
	for r in records:
		node = json_ld(r, base_url)
		node.pop("@context", None)
		graph.append(node)
	return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)


# -- Internet Archive -----------------------------------------------------------------------------


def ia_metadata(record: dict) -> dict:
	"""The item's metadata as the Internet Archive names it (for meta.xml, bulk upload and pushes)."""
	meta = {
		"title": record.get("title"),
		"alt_title": record.get("alt_title"),
		"creator": record.get("creators") or [],
		"alt_creator": [a for a in record.get("alt_creators") or [] if a],
		"date": record.get("date_raw") or (str(record["year"]) if record.get("year") else ""),
		"publisher": record.get("publisher"),
		"language": record.get("language"),
		"subject": record.get("subjects") or [],
		"description": record.get("description"),
		"volume": record.get("series"),
		"isbn": record.get("isbn"),
		"licenseurl": record.get("licence_url"),
		"rights": record.get("rights"),
		"mediatype": "texts",
	}
	return {k: v for k, v in meta.items() if v not in (None, "", [])}


def meta_xml(record: dict, collections: list[str] | None = None) -> str:
	meta = ia_metadata(record)
	lines = [f"  <identifier>{escape(record['item_id'])}</identifier>"]
	for key, value in meta.items():
		for v in value if isinstance(value, list) else [value]:
			lines.append(f"  <{key}>{escape(str(v))}</{key}>")
	for c in collections if collections is not None else record.get("collections") or []:
		lines.append(f"  <collection>{escape(c)}</collection>")
	return '<?xml version="1.0" encoding="UTF-8"?>\n<metadata>\n' + "\n".join(lines) + "\n</metadata>\n"


def ia_bulk_csv(records: list[dict], collection: str = "", file_for=None) -> str:
	"""The CSV the Internet Archive's bulk uploader (ia upload --spreadsheet) reads.
	Repeated fields become subject[0], subject[1], ...; `file_for(record)` names the file to upload."""
	metas = [ia_metadata(r) for r in records]
	width = {
		k: max((len(m.get(k) or []) for m in metas), default=0) for k in ("creator", "subject", "alt_creator")
	}
	header = ["identifier", "file", "mediatype", "collection", "title", "alt_title"]
	header += [f"creator[{i}]" for i in range(width["creator"])]
	header += [f"alt_creator[{i}]" for i in range(width["alt_creator"])]
	header += ["date", "publisher", "language", "volume", "isbn", "description", "licenseurl", "rights"]
	header += [f"subject[{i}]" for i in range(width["subject"])]
	out = io.StringIO()
	w = csv.DictWriter(out, fieldnames=header, extrasaction="ignore")
	w.writeheader()
	for r, m in zip(records, metas, strict=True):
		row = {k: v for k, v in m.items() if not isinstance(v, list)}
		row.update(
			{
				"identifier": r["item_id"],
				"file": file_for(r) if file_for else r.get("local_pdf") or "",
				"collection": collection or (r.get("collections") or [""])[0],
			}
		)
		for key in ("creator", "subject", "alt_creator"):
			for i, v in enumerate(m.get(key) or []):
				row[f"{key}[{i}]"] = v
		w.writerow(row)
	return out.getvalue()


# -- full JSON ------------------------------------------------------------------------------------

EXPORT_KEYS = (
	"item_id",
	"item_type",
	"title",
	"alt_title",
	"creators",
	"alt_creators",
	"year",
	"date_raw",
	"publisher",
	"place",
	"language",
	"language_label",
	"series",
	"isbn",
	"page_count",
	"description",
	"subjects",
	"collections",
	"curated_collections",
	"licence_url",
	"rights",
	"access_status",
	"visibility",
	"source",
	"source_url",
	"thumbnail_url",
	"ark",
	"has_fulltext",
	"has_page_text",
	"on_archive_org",
	"pdf_url",
)


def json_record(record: dict, base_url: str = "") -> dict:
	out = {k: record.get(k) for k in EXPORT_KEYS}
	out["portal_url"] = url_for(record, base_url) if base_url else ""
	out["citation_type"] = CITATION_TYPES.get(record.get("item_type") or "Book", CITATION_TYPES["Book"])[3]
	if record.get("modified"):
		out["modified"] = str(record["modified"])
	return out
