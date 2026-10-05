"""Reading MARC 21 bibliographic records from library systems (Koha, Evergreen, SOUL, e-Granthalaya,
Libsys, Alma exports…), and adding the links to a digital copy to them.

Records come as MARCXML (a ``<collection>`` of ``<record>``, what Koha's *Export catalog* and
OAI-PMH ``marc21`` give) or as ISO 2709 (``.mrc``, the classic binary exchange format, UTF-8).
A record is kept as a list of fields so it can be written back as it came, with only the
856 (electronic location) added.

Pure Python so it is unit-tested directly.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from xml.sax.saxutils import escape

MARC_NS = "http://www.loc.gov/MARC21/slim"
NS = "{" + MARC_NS + "}"
FT, SFD, RT = b"\x1e", b"\x1f", b"\x1d"  # field, subfield and record terminators (ISO 2709)


class MarcError(ValueError):
	pass


class Record:
	"""One MARC record: a leader, control fields (tag, value) and data fields
	(tag, ind1, ind2, [(code, value)]), in their order."""

	def __init__(self, leader: str = "", fields: list | None = None):
		self.leader = leader or " " * 24
		self.fields = fields or []

	def control(self, tag: str) -> str:
		return next((f[1] for f in self.fields if f[0] == tag and len(f) == 2), "")

	def data(self, *tags: str) -> list[tuple]:
		return [f for f in self.fields if f[0] in tags and len(f) == 4]

	def values(self, tag: str, codes: str = "a") -> list[str]:
		"""Each field's chosen subfields, joined: values("650", "a") → ["Kannada literature", …]."""
		out = []
		for _t, _i1, _i2, subs in self.data(tag):
			text = " ".join(v for c, v in subs if c in codes).strip()
			if text:
				out.append(text)
		return out

	def first(self, tag: str, codes: str = "a") -> str:
		found = self.values(tag, codes)
		return found[0] if found else ""

	def linked(self, tag: str, codes: str = "a") -> list[str]:
		"""The same field in its original script (880 with $6 pointing to `tag`)."""
		out = []
		for _t, _i1, _i2, subs in self.data("880"):
			link = next((v for c, v in subs if c == "6"), "")
			if link.startswith(tag):
				text = " ".join(v for c, v in subs if c in codes).strip()
				if text:
					out.append(text)
		return out


# -- reading --------------------------------------------------------------------------------------


def read(data: bytes) -> Iterator[Record]:
	"""Records from MARCXML or ISO 2709, whichever `data` is."""
	head = data.lstrip()[:200]
	if head.startswith(b"<") or b"<record" in head or b"<collection" in head:
		yield from read_xml(data)
	else:
		yield from read_iso2709(data)


def read_xml(data: bytes) -> Iterator[Record]:
	try:
		root = ET.fromstring(data)
	except ET.ParseError as e:
		raise MarcError(f"not MARCXML: {e}") from e
	records = (
		[root] if _local(root.tag) == "record" else [r for r in root.iter() if _local(r.tag) == "record"]
	)
	for rec in records:
		yield record_from_xml(rec)


def _local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1]


def record_from_xml(rec: ET.Element) -> Record:
	leader, fields = "", []
	for el in rec:
		name = _local(el.tag)
		if name == "leader":
			leader = el.text or ""
		elif name == "controlfield":
			fields.append((el.get("tag", ""), el.text or ""))
		elif name == "datafield":
			subs = [(s.get("code", ""), s.text or "") for s in el if _local(s.tag) == "subfield"]
			fields.append((el.get("tag", ""), el.get("ind1", " ") or " ", el.get("ind2", " ") or " ", subs))
	return Record(leader, fields)


def read_iso2709(data: bytes) -> Iterator[Record]:
	"""ISO 2709 records (UTF-8; MARC-8 records are read as Latin-1, best effort)."""
	for raw in data.split(RT):
		raw = raw.lstrip(b"\r\n ")
		if len(raw) < 25:
			continue
		leader = raw[:24].decode("ascii", "replace")
		try:
			base = int(leader[12:17])
		except ValueError as e:
			raise MarcError("not a MARC record (bad leader)") from e
		encoding = "utf-8" if leader[9] == "a" else "latin-1"
		directory = raw[24 : base - 1]
		fields = []
		for i in range(0, len(directory) - 11, 12):
			entry = directory[i : i + 12].decode("ascii", "replace")
			tag, length, start = entry[:3], int(entry[3:7]), int(entry[7:12])
			body = raw[base + start : base + start + length].rstrip(FT)
			if tag < "010" and tag.isdigit():
				fields.append((tag, body.decode(encoding, "replace")))
				continue
			ind = body[:2].decode(encoding, "replace").ljust(2)
			subs = []
			for part in body[2:].split(SFD)[1:]:
				if part:
					text = part.decode(encoding, "replace")
					subs.append((text[0], text[1:]))
			fields.append((tag, ind[0], ind[1], subs))
		yield Record(leader, fields)


# -- what a record says -------------------------------------------------------------------------

_TRAIL = re.compile(r"[\s/:;,=.]+$")
ARCHIVE_ID = re.compile(r"archive\.org/(?:details|download|stream)/([A-Za-z0-9._-]+)")


def clean(text: str) -> str:
	"""MARC's ISBD punctuation off the end ("Kannada sahitya charitre /" → "Kannada sahitya charitre")."""
	return _TRAIL.sub("", (text or "").strip()).strip()


def record_id(rec: Record) -> str:
	"""The library system's own number for the record: Koha's biblionumber (999 $c), else 001."""
	return rec.first("999", "c") or rec.control("001") or rec.first("035", "a")


def links(rec: Record) -> list[str]:
	return [u for u in rec.values("856", "u")]


def archive_ids(rec: Record) -> list[str]:
	"""archive.org identifiers the record already points to (856 $u)."""
	out = []
	for url in links(rec):
		m = ARCHIVE_ID.search(url)
		if m and m.group(1) not in out:
			out.append(m.group(1))
	return out


def isbns(rec: Record) -> list[str]:
	out = []
	for value in rec.values("020", "a"):
		digits = re.sub(r"[^0-9Xx]", "", value.split(" ")[0]).upper()
		if len(digits) in (10, 13):
			out.append(digits)
	return out


def summary(rec: Record) -> dict:
	"""The record as the catalogue reads it: {id, title, alt_title, creators, year, publisher,
	place, language, isbn, subjects, description, series, links, archive_ids}. A title in its own
	script (880 linked to 245) comes first, the romanised one as the other title."""
	roman = clean(rec.first("245", "ab"))
	script = clean((rec.linked("245", "ab") or [""])[0])
	title, alt = (script, roman) if script else (roman, clean(rec.first("246", "ab")))
	creators = [clean(v) for v in rec.values("100", "a") + rec.values("110", "a") + rec.values("700", "a")]
	year = ""
	for v in rec.values("264", "c") + rec.values("260", "c"):
		m = re.search(r"\b(1[4-9]\d\d|20\d\d)\b", v)
		if m:
			year = m.group(1)
			break
	f008 = rec.control("008")
	if not year and len(f008) >= 11 and f008[7:11].isdigit():
		year = f008[7:11]
	language = f008[35:38].strip() if len(f008) >= 38 else ""
	language = language if language and language not in ("|||", "zxx", "und") else rec.first("041", "a")[:3]
	return {
		"id": record_id(rec),
		"title": title,
		"alt_title": alt if alt != title else "",
		"creators": [c for c in dict.fromkeys(creators) if c],
		"year": year,
		"publisher": clean(rec.first("264", "b") or rec.first("260", "b")),
		"place": clean(rec.first("264", "a") or rec.first("260", "a")),
		"language": language,
		"isbn": (isbns(rec) or [""])[0],
		"subjects": [
			clean(v) for v in rec.values("650", "a") + rec.values("651", "a") + rec.values("600", "a")
		],
		"description": " ".join(rec.values("520", "a")),
		"series": clean(rec.first("490", "a")),
		"links": links(rec),
		"archive_ids": archive_ids(rec),
	}


def to_meta(summary_: dict, collection: str = "") -> dict:
	"""archive.org-style metadata, for the catalogue's clean-up (normalize_ia_item)."""
	meta = {
		"title": [summary_["title"]] if summary_["title"] else [],
		"creator": summary_["creators"],
		"date": summary_["year"],
		"publisher": [summary_["publisher"]] if summary_["publisher"] else [],
		"place": summary_["place"],
		"language": [summary_["language"]] if summary_["language"] else [],
		"subject": summary_["subjects"],
		"description": [summary_["description"]] if summary_["description"] else [],
		"isbn": summary_["isbn"],
		"volume": summary_["series"],
	}
	if summary_.get("alt_title"):
		meta["alt_title"] = summary_["alt_title"]
	if collection:
		meta["collection"] = [collection]
	return {k: v for k, v in meta.items() if v}


# -- writing back ------------------------------------------------------------------------------------


def with_links(rec: Record, urls: list[tuple[str, str]]) -> Record:
	"""The record with an 856 4 1 (a version of the resource) for each (url, note) it lacks."""
	have = set(links(rec))
	fields = list(rec.fields)
	for url, note in urls:
		if url and url not in have:
			have.add(url)
			fields.append(("856", "4", "1", [("u", url), *([("z", note)] if note else [])]))
	return Record(rec.leader, fields)


def to_xml(rec: Record) -> str:
	out = [f'<record xmlns="{MARC_NS}">', f"<leader>{escape(rec.leader)}</leader>"]
	for f in rec.fields:
		if len(f) == 2:
			out.append(f'<controlfield tag="{escape(f[0])}">{escape(f[1])}</controlfield>')
		else:
			tag, i1, i2, subs = f
			inner = "".join(f'<subfield code="{escape(c)}">{escape(v)}</subfield>' for c, v in subs)
			out.append(
				f'<datafield tag="{escape(tag)}" ind1="{escape(i1)}" ind2="{escape(i2)}">{inner}</datafield>'
			)
	out.append("</record>")
	return "".join(out)


def collection_xml(records: list[Record]) -> str:
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		f'<collection xmlns="{MARC_NS}">\n'
		+ "\n".join(to_xml(r).replace(f' xmlns="{MARC_NS}"', "") for r in records)
		+ "\n</collection>\n"
	)
