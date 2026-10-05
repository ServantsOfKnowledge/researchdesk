"""A Calibre library as a store of books (the same interface as the IA-style item folders).

A Calibre library is a folder with a ``metadata.db`` (SQLite) and, for every book, a folder
``<Author>/<Title> (<id>)/`` holding its files (``<name>.epub``, ``.pdf``, ``.mobi``…),
``cover.jpg`` and ``metadata.opf``. This reads the database **read-only** (the library is never
changed) and turns each book into the metadata an archive.org item has, so the whole ingest
machinery (catalogue, covers, PDF text, search, access) works on it unchanged.

Pure Python (no Frappe) so it is unit-tested directly.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections.abc import Iterator

from sok_resdesk.core.folder import ItemStore, StoreError

DB = "metadata.db"
PREFIX = "calibre-"
# Calibre's "no date" is 0101-01-01; anything before the year 1000 is not a real publication date
NO_DATE_BEFORE = 1000
COVER = "cover.jpg"
OPF = "metadata.opf"


def is_library(path: str) -> bool:
	return os.path.isfile(os.path.join(path, DB))


def book_id(uuid: str) -> str:
	"""A book's identifier here: from Calibre's own uuid, so it survives a rebuilt library."""
	return PREFIX + re.sub(r"[^0-9a-z]", "", (uuid or "").lower())[:12]


def _text(value) -> str:
	return (value or "").strip() if isinstance(value, str) else ""


def _date(value) -> str:
	"""'2019-03-01 00:00:00+00:00' → '2019-03-01', or '' for Calibre's no-date placeholder."""
	m = re.match(r"(\d{4})-(\d\d)-(\d\d)", _text(value))
	if not m or int(m.group(1)) < NO_DATE_BEFORE:
		return ""
	return m.group(0)


class CalibreStore(ItemStore):
	kind = "calibre"

	def __init__(self, root: str):
		self.root = os.path.realpath(root)
		if not is_library(self.root):
			raise StoreError(f"No Calibre library (metadata.db) in {root}")
		self._books: dict[str, dict] | None = None  # path → the book, loaded once

	# -- the database --------------------------------------------------------------------------------

	def _connect(self) -> sqlite3.Connection:
		# read-only: opening a library here never writes to it (no journal, no schema upgrade)
		con = sqlite3.connect(f"file:{os.path.join(self.root, DB)}?mode=ro", uri=True, timeout=30)
		con.row_factory = sqlite3.Row
		return con

	@staticmethod
	def _many(con, sql: str) -> dict[int, list]:
		out: dict[int, list] = {}
		try:
			for r in con.execute(sql):
				out.setdefault(r[0], []).append(tuple(r)[1:] if len(r) > 2 else r[1])
		except sqlite3.OperationalError:  # a table this Calibre version does not have
			pass
		return out

	def _load(self) -> dict[str, dict]:
		if self._books is not None:
			return self._books
		con = self._connect()
		try:
			authors = self._many(
				con,
				"select l.book, a.name from books_authors_link l join authors a on a.id = l.author order by l.id",
			)
			tags = self._many(
				con,
				"select l.book, t.name from books_tags_link l join tags t on t.id = l.tag order by t.name",
			)
			publishers = self._many(
				con,
				"select l.book, p.name from books_publishers_link l join publishers p on p.id = l.publisher",
			)
			series = self._many(
				con, "select l.book, s.name from books_series_link l join series s on s.id = l.series"
			)
			langs = self._many(
				con,
				"select l.book, g.lang_code from books_languages_link l join languages g on g.id = l.lang_code"
				" order by l.item_order",
			)
			comments = self._many(con, "select book, text from comments")
			ratings = self._many(
				con, "select l.book, r.rating from books_ratings_link l join ratings r on r.id = l.rating"
			)
			idents = self._many(con, "select book, type, val from identifiers")
			formats = self._many(con, "select book, format, name, uncompressed_size from data order by id")
			custom = self._custom(con)
			books = {}
			for r in con.execute(
				"select id, title, uuid, path, pubdate, timestamp, last_modified, series_index, has_cover, isbn from books"
			):
				if not r["path"] or not r["uuid"]:
					continue
				i = r["id"]
				books[r["path"]] = {
					"id": i,
					"uuid": r["uuid"],
					"title": _text(r["title"]),
					"path": r["path"],
					"pubdate": _date(r["pubdate"]),
					"added": _date(r["timestamp"]),
					"modified": _text(str(r["last_modified"] or "")),
					"series_index": r["series_index"],
					"has_cover": bool(r["has_cover"]),
					"isbn": _text(r["isbn"]),
					# Calibre keeps a comma in a name as "|"
					"authors": [a.replace("|", ",") for a in authors.get(i, [])],
					"tags": tags.get(i, []),
					"publisher": (publishers.get(i) or [""])[0],
					"series": (series.get(i) or [""])[0],
					"languages": langs.get(i, []),
					"comments": (comments.get(i) or [""])[0],
					"rating": (ratings.get(i) or [0])[0],
					"identifiers": {t: v for t, v in idents.get(i, [])},
					"formats": [(f, n, s) for f, n, s in formats.get(i, [])],
					"custom": custom.get(i, {}),
				}
		finally:
			con.close()
		self._books = books
		return books

	def _custom(self, con) -> dict[int, dict[str, str]]:
		"""{book: {column name: value as text}} of the library's custom columns."""
		out: dict[int, dict[str, str]] = {}
		try:
			columns = list(con.execute("select id, label, name, datatype, normalize from custom_columns"))
		except sqlite3.OperationalError:
			return out
		for c in columns:
			if c["datatype"] == "composite":  # computed in Calibre, nothing stored
				continue
			n = c["id"]
			if c["normalize"]:
				sql = (
					f"select l.book, v.value from books_custom_column_{n}_link l "
					f"join custom_column_{n} v on v.id = l.value"
				)
			else:
				sql = f"select book, value from custom_column_{n}"
			for book, values in self._many(con, sql).items():
				text = ", ".join(str(v) for v in values if v not in (None, ""))
				if text:
					out.setdefault(book, {})[c["name"]] = text
		return out

	def _book(self, loc: str) -> dict:
		book = self._load().get(loc)
		if not book:
			raise StoreError(f"{loc}: not in this Calibre library")
		return book

	# -- the store interface -------------------------------------------------------------------------

	def iter_items(self, limit: int = 0) -> Iterator[tuple[str, str]]:
		for n, b in enumerate(sorted(self._load().values(), key=lambda b: b["id"])):
			if limit and n >= limit:
				return
			yield book_id(b["uuid"]), b["path"]

	def _path(self, loc: str, name: str = "") -> str:
		path = os.path.realpath(os.path.join(self.root, loc, name))
		if path != self.root and not path.startswith(self.root + os.sep):
			raise StoreError("path outside the library folder")
		return path

	@staticmethod
	def _file_name(name: str, fmt: str) -> str:
		return f"{name}.{fmt.lower()}"

	def format_files(self, loc: str) -> list[str]:
		"""The book's files in its formats that exist on disk (Calibre's records can outlive a file)."""
		return [
			f
			for f in (self._file_name(n, fmt) for fmt, n, _size in self._book(loc)["formats"])
			if os.path.isfile(self._path(loc, f))
		]

	def list_files(self, loc: str) -> list[str]:
		files = self.format_files(loc)
		for extra in (COVER, OPF):
			if os.path.isfile(self._path(loc, extra)):
				files.append(extra)
		return files

	def read(self, loc: str, name: str) -> bytes | None:
		path = self.file_path(loc, name)
		if not path:
			return None
		with open(path, "rb") as f:
			return f.read()

	def file_path(self, loc: str, name: str) -> str | None:
		self._book(loc)
		path = self._path(loc, name)
		return path if os.path.isfile(path) else None

	def signature(self, loc: str, identifier: str) -> str:
		b = self._book(loc)
		sizes = "|".join(f"{f}:{s}" for f, _n, s in b["formats"])
		return hashlib.sha1(f"{b['modified']}|{sizes}|{int(b['has_cover'])}".encode()).hexdigest()[:16]

	def load_item(self, identifier: str, loc: str) -> dict:
		b = self._book(loc)
		series = f"{b['series']} #{b['series_index']:g}" if b["series"] and b["series_index"] else b["series"]
		meta = {
			"identifier": identifier,
			"title": b["title"],
			"creator": b["authors"],
			"date": b["pubdate"],
			"publisher": b["publisher"],
			"language": b["languages"],
			"subject": b["tags"],
			"description": b["comments"],
			"series": series,
			"isbn": b["isbn"] or b["identifiers"].get("isbn", ""),
			"addeddate": b["added"],
			# kept in the record's raw metadata, for the cataloguer
			"calibre": {
				"id": b["id"],
				"uuid": b["uuid"],
				"rating": b["rating"],
				"identifiers": b["identifiers"],
				"custom": b["custom"],
			},
		}
		return {
			"metadata": {k: v for k, v in meta.items() if v not in ("", [], None)},
			"files": [{"name": f} for f in self.list_files(loc)],
			"page_numbers": None,
		}

	def page_texts(self, identifier: str, loc: str, page_numbers=None) -> tuple[list[dict], str]:
		return [], ""  # a PDF's text is read from the PDF; other formats are catalogued, not read

	def book_text(self, identifier: str, loc: str) -> str:
		return ""

	def scan_leaves(self, identifier: str, loc: str, files=None) -> list:
		return []

	def pdf_name(self, identifier: str, loc: str) -> str | None:
		pdfs = sorted(f for f in self.format_files(loc) if f.lower().endswith(".pdf"))
		return pdfs[0] if pdfs else None

	def thumb_name(self, loc: str) -> str | None:
		return COVER if self._book(loc)["has_cover"] and os.path.isfile(self._path(loc, COVER)) else None

	def downloads(self, loc: str) -> list[str]:
		"""Every format file of the book: what a reader may download."""
		return self.format_files(loc)
