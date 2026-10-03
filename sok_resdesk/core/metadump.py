"""Metadata files to ingest from: a whole collection's records in one file. Pure Python.

The fastest way to build a large catalogue is to have every book's metadata in hand before any
request to archive.org. Research Desk reads these files (gzip-compressed or not):

* **JSON Lines from ``ia search``**: one search record per line, as
  ``ia search "collection:ServantsOfKnowledge" -f title -f creator -f date … > books.jsonl``
  writes them: ``{"identifier": "…", "title": "…", …}``;
* **JSON Lines from ``ia metadata``**: one full item record per line,
  ``{"metadata": {…}, "files": […]}``, as ``ia metadata <id>`` prints it (with the file list
  the book is catalogued completely, no archive.org request needed);
* **a JSON array** of either;
* **CSV or TSV** with an ``identifier`` column (as archive.org's search exports and
  spreadsheets have); several values in one cell split on ``;`` or ``|``, and IA's
  ``subject[0]``, ``subject[1]`` columns are joined into one list;
* **a plain list** of identifiers, one per line.

Lines that can't be read are counted and left out; a record without an identifier too.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,99}$")
INDEXED = re.compile(r"^(.+)\[\d+\]$")
MULTI = re.compile(r"\s*[;|]\s*")
LIST_FIELDS = {"creator", "subject", "collection", "language", "format", "alt_creator", "description"}


class DumpError(ValueError):
	pass


def _text(data: bytes) -> str:
	if data[:2] == b"\x1f\x8b":
		data = gzip.decompress(data)
	for enc in ("utf-8-sig", "utf-16"):
		try:
			return data.decode(enc)
		except UnicodeDecodeError:
			continue
	return data.decode("utf-8", errors="replace")


def _flat(obj: dict) -> dict | None:
	"""A search record or an `ia metadata` record → {identifier, fields…, _files?}."""
	if not isinstance(obj, dict):
		return None
	if isinstance(obj.get("metadata"), dict):  # ia metadata <id>
		row = dict(obj["metadata"])
		if isinstance(obj.get("files"), list):
			row["_files"] = obj["files"]
	else:
		row = dict(obj)
	ident = row.get("identifier")
	if isinstance(ident, list):
		ident = ident[0] if ident else ""
	ident = str(ident or "").strip()
	if not ID.match(ident):
		return None
	row["identifier"] = ident
	return row


def _from_csv(text: str, dialect: str) -> tuple[list[dict], int]:
	reader = csv.DictReader(io.StringIO(text), dialect=dialect)
	rows, bad = [], 0
	for raw in reader:
		row: dict = {}
		for key, value in raw.items():
			if key is None or value is None:
				continue
			key, value = key.strip(), value.strip()
			if not value:
				continue
			m = INDEXED.match(key)
			if m:  # subject[0], subject[1] …
				row.setdefault(m.group(1), []).append(value)
			elif key in LIST_FIELDS and key != "description" and MULTI.search(value):
				row[key] = [v for v in MULTI.split(value) if v]
			else:
				row[key] = value
		flat = _flat(row)
		if flat:
			rows.append(flat)
		else:
			bad += 1
	return rows, bad


def read(data: bytes, name: str = "") -> dict:
	"""Read a metadata file. Returns {rows, bad, kind, complete}: the records (each with an
	`identifier`, and `_files` when the file had full item records), how many lines were left
	out, what kind of file it was, and how many records are complete."""
	text = _text(data).strip()
	if not text:
		raise DumpError("The file is empty")
	lower = name.lower().removesuffix(".gz")
	rows: list[dict] = []
	bad = 0
	if text[:1] == "[":
		try:
			items = json.loads(text)
		except ValueError as e:
			raise DumpError(f"The JSON could not be read: {e}") from e
		kind = "json"
		for obj in items if isinstance(items, list) else []:
			flat = _flat(obj)
			if flat:
				rows.append(flat)
			else:
				bad += 1
	elif text[:1] == "{":
		kind = "jsonl"
		for line in text.splitlines():
			line = line.strip()
			if not line:
				continue
			try:
				flat = _flat(json.loads(line))
			except ValueError:
				flat = None
			if flat:
				rows.append(flat)
			else:
				bad += 1
	else:
		first = text.splitlines()[0]
		if lower.endswith((".csv", ".tsv")) or (
			"identifier" in first.lower() and ("," in first or "\t" in first)
		):
			kind = "tsv" if lower.endswith(".tsv") or ("\t" in first and "," not in first) else "csv"
			rows, bad = _from_csv(text, "excel-tab" if kind == "tsv" else "excel")
			if not rows and bad:
				raise DumpError(
					"No row has an identifier: the first line must name the columns, one of them `identifier`"
				)
		else:
			kind = "identifiers"
			for line in text.splitlines():
				ident = line.strip().split()[0] if line.strip() else ""
				if not ident or ident.startswith("#"):
					continue
				if ID.match(ident):
					rows.append({"identifier": ident})
				else:
					bad += 1
	seen: dict[str, dict] = {}
	for row in rows:  # the last record of an identifier wins (a later export corrects an earlier one)
		seen[row["identifier"]] = row
	rows = list(seen.values())
	return {
		"rows": rows,
		"bad": bad,
		"kind": kind,
		"complete": sum(1 for r in rows if "_files" in r),
	}


def only_identifiers(row: dict) -> bool:
	"""A record that names its book and nothing else (an identifier list)."""
	return set(row) <= {"identifier"}
