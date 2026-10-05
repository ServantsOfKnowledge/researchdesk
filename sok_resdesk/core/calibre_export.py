"""A set of books written as a folder Calibre can add: ``Author/Title (n)/`` with each book's files,
a ``metadata.opf`` (its details, in Calibre's own sidecar format) and ``cover.jpg``, in one zip.

Only files the library holds are put in. Books it does not hold the file of (archive.org-only,
a repository's, a book server's) are listed in ``not-included.csv`` with a link, so the person
can fetch them where they live. Pure Python (no Frappe) so it is unit-tested directly.
"""

from __future__ import annotations

import csv
import io
import os
import re
import uuid
import zipfile
from xml.sax.saxutils import escape, quoteattr

NS = uuid.UUID("6f0f3a6e-5b1d-4c43-9a43-0c5d2b6c1a11")  # makes a book's Calibre uuid from its identifier
UNPACKED = (".epub", ".pdf", ".mobi", ".azw3", ".jpg", ".jpeg", ".png", ".djvu", ".cbz", ".zip", ".docx")
README = """This folder was made by SOK Research Desk for Calibre.

To add the books: in Calibre choose  Add books > Add books from directories, including
sub-directories (Assume each directory has a single logical book),  and pick the folder you
unpacked this into. Or, on a command line:

    calibredb add --recurse --one-book-per-directory "<the unpacked folder>"

Each book's folder holds its files (every format together), metadata.opf (its details) and
cover.jpg when it has one.

Books whose files this library does not hold are listed in not-included.csv with a link to
where they are (archive.org, a repository, a book server): get them there, or import them into
a Research Desk of your own.
"""


def clean(text: str, limit: int = 60) -> str:
	"""A name that is safe as a file or folder name on any system."""
	text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text or "")
	text = re.sub(r"\s+", " ", text).strip(" .")
	return text[:limit].rstrip(" .") or "Unknown"


def book_uuid(item_id: str) -> str:
	return str(uuid.uuid5(NS, item_id))


def _tag(name: str, value, attrs: str = "") -> str:
	return f"    <{name}{attrs}>{escape(str(value))}</{name}>\n" if value not in (None, "") else ""


def opf(book: dict) -> str:
	"""Calibre's metadata.opf for one book (the keys of `books` below)."""
	out = [
		"<?xml version='1.0' encoding='utf-8'?>\n",
		'<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id" version="2.0">\n',
		'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">\n',
		f'    <dc:identifier opf:scheme="calibre" id="calibre_id">{escape(book["uuid"])}</dc:identifier>\n',
		f'    <dc:identifier opf:scheme="uuid" id="uuid_id">{escape(book["uuid"])}</dc:identifier>\n',
		_tag("dc:title", book["title"]),
	]
	for a in book.get("authors") or []:
		out.append(_tag("dc:creator", a, f' opf:role="aut" opf:file-as={quoteattr(a)}'))
	if book.get("date"):
		out.append(_tag("dc:date", f"{book['date']}T00:00:00+00:00"))
	out.append(_tag("dc:description", book.get("description")))
	out.append(_tag("dc:publisher", book.get("publisher")))
	for scheme, value in (book.get("identifiers") or {}).items():
		out.append(_tag("dc:identifier", value, f" opf:scheme={quoteattr(scheme)}"))
	out.append(_tag("dc:language", book.get("language")))
	for t in book.get("tags") or []:
		out.append(_tag("dc:subject", t))
	if book.get("series"):
		out.append(f'    <meta name="calibre:series" content={quoteattr(book["series"])}/>\n')
		out.append(f'    <meta name="calibre:series_index" content="{book.get("series_index") or 1}"/>\n')
	out.append("  </metadata>\n")
	if book.get("cover"):
		out.append('  <guide>\n    <reference type="cover" title="Cover" href="cover.jpg"/>\n  </guide>\n')
	out.append("</package>\n")
	return "".join(out)


def layout(books: list[dict]) -> list[str]:
	"""The folder of each book, Calibre's way: `Author/Title (n)`; n is made unique."""
	paths, used = [], set()
	for n, b in enumerate(books, 1):
		author = clean((b.get("authors") or ["Unknown"])[0], 40)
		folder = f"{author}/{clean(b['title'], 60)} ({n})"
		while folder in used:  # not reached while n is unique, kept for safety
			folder += "_"
		used.add(folder)
		paths.append(folder)
	return paths


def file_name(book: dict, ext: str) -> str:
	author = clean((book.get("authors") or ["Unknown"])[0], 30)
	return f"{clean(book['title'], 60)} - {author}{ext}"


def total_size(books: list[dict]) -> int:
	size = 0
	for b in books:
		for path in [p for _n, p in b.get("files", [])] + ([b["cover"]] if b.get("cover") else []):
			try:
				size += os.path.getsize(path)
			except OSError:
				pass
	return size


def not_included_csv(rows: list[dict]) -> str:
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(["identifier", "title", "authors", "year", "why not included", "where it is"])
	for r in rows:
		w.writerow(
			[
				r["item_id"],
				r["title"],
				"; ".join(r.get("authors") or []),
				r.get("year") or "",
				r["why"],
				r.get("link") or "",
			]
		)
	return buf.getvalue()


def write_zip(dest: str, books: list[dict], not_included: list[dict] | None = None, progress=None) -> int:
	"""Write the zip at `dest`; each book is {item_id, title, authors, …, files: [(name, path)], cover}.
	Returns the number of files put in."""
	folders = layout(books)
	count = 0
	with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
		z.writestr("README.txt", README)
		z.writestr("not-included.csv", not_included_csv(not_included or []))
		for n, (b, folder) in enumerate(zip(books, folders, strict=True)):
			z.writestr(f"{folder}/metadata.opf", opf(b))
			names = set()
			for name, path in b.get("files", []):
				ext = os.path.splitext(name)[1].lower()
				target = file_name(b, ext)
				while target in names:  # two files of one format: keep both
					target = f"{os.path.splitext(target)[0]} ({len(names)}){ext}"
				names.add(target)
				z.write(
					path,
					f"{folder}/{target}",
					zipfile.ZIP_STORED if ext in UNPACKED else zipfile.ZIP_DEFLATED,
				)
				count += 1
			if b.get("cover"):
				z.write(b["cover"], f"{folder}/cover.jpg", zipfile.ZIP_STORED)
			if progress:
				progress(n + 1)
	return count
