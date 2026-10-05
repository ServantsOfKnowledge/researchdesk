"""Books stored as Internet-Archive-style item folders, on disk or on a web server.

An *item folder* is what the IA/Scribe/Repub pipeline produces:

    <root>/<anything>/<identifier>/
        <identifier>_meta.xml                 metadata (IA schema)
        <identifier>_hocr_searchtext.txt.gz   page text  } preferred
        <identifier>_hocr_pageindex.json.gz   page index }
        <identifier>_hocr.html / _chocr.html.gz   hOCR (fallback)
        <identifier>_djvu.xml / _djvu.txt     DjVu text (fallback)
        <identifier>_page_numbers.json        printed page numbers (optional)
        <identifier>.pdf, __ia_thumb.jpg, _jp2.zip …

Two stores share one interface:

* ``FolderStore``: a directory on this machine (local disk, USB, NAS mount).
  Item folders may be nested at any depth; an item is any folder holding a
  ``*_meta.xml``.
* ``FolderStore`` also takes **loose PDFs**: in a folder with no ``*_meta.xml``, each PDF is a
  book of its own (``theses/2019/Some thesis.pdf`` → ``Some-thesis``), catalogued from what the
  PDF says about itself (title, author) and its file name. Its text is the PDF's text layer, or
  OCR here for a scan (pdfs.py).
* ``HttpStore``: a web server exposing the same layout
  (``<base>/<identifier>/<file>``). Items are listed from a manifest
  (``identifiers.txt``, one relative path per line) or from the server's
  directory listing (nginx ``autoindex`` / Apache ``Indexes``).

Pure Python (no Frappe) so it is unit-tested directly.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

from sok_resdesk.core import scandata

META_SUFFIX = "_meta.xml"
SERVABLE = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".txt", ".epub", ".webp"}
MAX_SCAN_DEPTH = 6


class StoreError(Exception):
	pass


# -- metadata ------------------------------------------------------------------------------


def parse_meta_xml(data: bytes) -> dict:
	"""IA ``_meta.xml`` → dict. Repeated tags become lists (as in the metadata API)."""
	try:
		root = ET.fromstring(data)
	except ET.ParseError as exc:
		raise StoreError(f"invalid _meta.xml: {exc}") from exc
	meta: dict = {}
	for el in root:
		key, value = el.tag, (el.text or "").strip()
		if not value:
			continue
		if key in meta:
			if not isinstance(meta[key], list):
				meta[key] = [meta[key]]
			meta[key].append(value)
		else:
			meta[key] = value
	return meta


# -- page text ------------------------------------------------------------------------------


def pages_from_searchtext(
	text_gz: bytes, index_gz: bytes, page_numbers: dict | None = None, leaves: list | None = None
) -> list[dict]:
	"""`leaves`: the scan data (core/scandata.py), so each text goes with its page image."""
	text = gzip.decompress(text_gz).decode("utf-8", errors="replace")
	index = json.loads(gzip.decompress(index_gz))
	return scandata.pages([text[e[0] : e[1]] for e in index], page_numbers, leaves)


class _HocrParser(HTMLParser):
	"""Streams hOCR (and IA's character-level chOCR): one text block per ocr_page."""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.pages: list[list[str]] = []
		self.stack: list[str] = []  # class of each open element
		self.word: list[str] | None = None
		self.line: list[str] = []

	def handle_starttag(self, tag, attrs):
		cls = dict(attrs).get("class") or ""
		self.stack.append(cls)
		if "ocr_page" in cls:
			self.pages.append([])
		elif "ocrx_word" in cls:
			self.word = []

	def handle_endtag(self, tag):
		if not self.stack:
			return
		cls = self.stack.pop()
		if "ocrx_word" in cls and self.word is not None:
			w = "".join(self.word).strip()
			if w:
				self.line.append(w)
			self.word = None
		elif "ocr_line" in cls or "ocr_par" in cls:
			self._flush_line()
		elif "ocr_page" in cls:
			self._flush_line()

	def handle_data(self, data):
		if self.word is not None:
			self.word.append(data.strip())

	def _flush_line(self):
		if self.line and self.pages:
			self.pages[-1].append(" ".join(self.line))
		self.line = []


def pages_from_hocr(html: bytes, page_numbers: dict | None = None, leaves: list | None = None) -> list[dict]:
	parser = _HocrParser()
	chunk = 1 << 20
	text = html.decode("utf-8", errors="replace")
	for i in range(0, len(text), chunk):
		parser.feed(text[i : i + chunk])
	parser.close()
	return scandata.pages(["\n".join(lines) for lines in parser.pages], page_numbers, leaves)


def pages_from_djvu_xml(
	data: bytes, page_numbers: dict | None = None, leaves: list | None = None
) -> list[dict]:
	texts: list[str] = []
	words: list[str] = []
	lines: list[str] = []
	for event, el in ET.iterparse(_BytesIO(data), events=("start", "end")):
		tag = el.tag
		if event == "start" and tag == "OBJECT":
			lines = []
		elif event == "end":
			if tag == "WORD":
				if el.text and el.text.strip():
					words.append(el.text.strip())
			elif tag == "LINE":
				if words:
					lines.append(" ".join(words))
				words = []
			elif tag == "OBJECT":
				if words:
					lines.append(" ".join(words))
					words = []
				texts.append("\n".join(lines))
				el.clear()
	return scandata.pages(texts, page_numbers, leaves)


def _BytesIO(data: bytes):
	import io

	return io.BytesIO(data)


# -- stores ---------------------------------------------------------------------------------


class ItemStore:
	"""Common interface. ``loc`` is the item's location relative to the store root."""

	kind = "base"

	def iter_items(self, limit: int = 0) -> Iterator[tuple[str, str]]:
		"""Yield (identifier, loc)."""
		raise NotImplementedError

	def list_files(self, loc: str) -> list[str]:
		raise NotImplementedError

	def read(self, loc: str, name: str) -> bytes | None:
		raise NotImplementedError

	def signature(self, loc: str, identifier: str) -> str:
		"""Changes when the item's metadata or text changes (for re-ingest on update)."""
		raise NotImplementedError

	def public_url(self, loc: str, name: str) -> str | None:
		return None

	# shared helpers
	def meta_name(self, loc: str, identifier: str | None = None) -> str | None:
		files = self.list_files(loc)
		if identifier and f"{identifier}{META_SUFFIX}" in files:
			return f"{identifier}{META_SUFFIX}"
		return next((f for f in files if f.endswith(META_SUFFIX)), None)

	def load_item(self, identifier: str, loc: str) -> dict:
		"""Metadata + file list for one item, in the shape IA's metadata API returns."""
		files = self.list_files(loc)
		name = self.meta_name(loc, identifier)
		if not name:
			raise StoreError(f"{loc}: no _meta.xml")
		meta = parse_meta_xml(self.read(loc, name) or b"")
		meta.setdefault("identifier", identifier)
		page_numbers = None
		pn = f"{identifier}_page_numbers.json"
		if pn in files:
			try:
				page_numbers = json.loads(self.read(loc, pn) or b"{}")
			except ValueError:
				page_numbers = None
		return {"metadata": meta, "files": [{"name": f} for f in files], "page_numbers": page_numbers}

	def scan_leaves(self, identifier: str, loc: str, files: set[str] | None = None) -> list:
		"""The item's scan data (core/scandata.py): which leaves the book shows."""
		files = files if files is not None else set(self.list_files(loc))
		name = scandata.file_name(identifier, sorted(files))
		if not name:
			return []
		data = self.read(loc, name)
		return scandata.parse(scandata.from_zip(data) if name.endswith(".zip") else data)

	def page_texts(
		self, identifier: str, loc: str, page_numbers: dict | None = None
	) -> tuple[list[dict], str]:
		"""Best available page text. Returns (pages, source-file-used)."""
		files = set(self.list_files(loc))
		i = identifier
		leaves = self.scan_leaves(identifier, loc, files)
		if f"{i}_hocr_searchtext.txt.gz" in files and f"{i}_hocr_pageindex.json.gz" in files:
			text, index = (
				self.read(loc, f"{i}_hocr_searchtext.txt.gz"),
				self.read(loc, f"{i}_hocr_pageindex.json.gz"),
			)
			if text and index:
				return pages_from_searchtext(text, index, page_numbers, leaves), "hocr_searchtext"
		for name, gz in (
			(f"{i}_hocr.html", False),
			(f"{i}_hocr.html.gz", True),
			(f"{i}_chocr.html.gz", True),
			(f"{i}_chocr.html", False),
		):
			if name in files:
				data = self.read(loc, name)
				if data:
					return pages_from_hocr(
						gzip.decompress(data) if gz else data, page_numbers, leaves
					), name.split("_")[-1]
		if f"{i}_djvu.xml" in files:
			data = self.read(loc, f"{i}_djvu.xml")
			if data:
				return pages_from_djvu_xml(data, page_numbers, leaves), "djvu.xml"
		return [], ""

	def book_text(self, identifier: str, loc: str) -> str:
		"""Whole-book plain text (only used when there is no page-level text)."""
		name = f"{identifier}_djvu.txt"
		if name in self.list_files(loc):
			data = self.read(loc, name)
			return data.decode("utf-8", errors="replace") if data else ""
		return ""

	def pdf_name(self, identifier: str, loc: str) -> str | None:
		files = self.list_files(loc)
		if f"{identifier}.pdf" in files:
			return f"{identifier}.pdf"
		pdfs = sorted(f for f in files if f.lower().endswith(".pdf") and not f.endswith("_text.pdf"))
		return pdfs[0] if pdfs else None

	def thumb_name(self, loc: str) -> str | None:
		files = self.list_files(loc)
		for name in ("__ia_thumb.jpg", "cover.jpg", "thumbnail.jpg"):
			if name in files:
				return name
		return None


def bare_id(file_name: str) -> str:
	"""A catalogue identifier for a loose PDF, from its file name: letters, digits, dots,
	hyphens and underscores, as archive.org identifiers (``Some thesis (2019).pdf`` →
	``Some-thesis-2019``)."""
	stem = os.path.splitext(os.path.basename(file_name))[0]
	safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")[:90]
	return safe or "pdf-" + hashlib.sha1(stem.encode()).hexdigest()[:10]


_JUNK_TITLE = re.compile(r"^(untitled|microsoft word - |document\d*$|scan\d*$|img\d*|\s*$)", re.I)


def bare_meta(identifier: str, file_name: str, info: dict) -> dict:
	"""IA-style metadata for a loose PDF: the PDF's own title and author when they look like a
	book's (not "Microsoft Word - draft.docx" or "Scan0001"), else its file name."""
	title = info.get("title") or ""
	if _JUNK_TITLE.match(title) or title.lower().endswith((".doc", ".docx", ".pdf", ".tif")):
		title = ""
	stem = os.path.splitext(os.path.basename(file_name))[0]
	meta = {
		"identifier": identifier,
		"title": title or re.sub(r"[_]+|\s{2,}", " ", stem).strip(),
		"mediatype": "texts",
	}
	if info.get("author") and not _JUNK_TITLE.match(info["author"]):
		meta["creator"] = [a.strip() for a in re.split(r";|\band\b", info["author"]) if a.strip()]
	if info.get("keywords"):
		meta["subject"] = [k.strip() for k in re.split(r"[;,]", info["keywords"]) if k.strip()]
	if info.get("subject"):
		meta["description"] = info["subject"]
	return meta


def is_bare(loc: str) -> bool:
	"""A loose PDF's location is the PDF's own path."""
	return loc.lower().endswith(".pdf")


class FolderStore(ItemStore):
	kind = "folder"

	def __init__(self, root: str):
		self.root = os.path.realpath(root)
		if not os.path.isdir(self.root):
			raise StoreError(f"Folder not found: {root}")

	def _path(self, loc: str, name: str = "") -> str:
		path = os.path.realpath(os.path.join(self.root, loc, name))
		if path != self.root and not path.startswith(self.root + os.sep):
			raise StoreError("path outside the library folder")
		return path

	def iter_items(self, limit: int = 0) -> Iterator[tuple[str, str]]:
		seen = 0
		base_depth = self.root.rstrip(os.sep).count(os.sep)
		for dirpath, dirnames, filenames in os.walk(self.root):
			dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "@", "#")))
			if dirpath.count(os.sep) - base_depth >= MAX_SCAN_DEPTH:
				dirnames[:] = []
			metas = [f for f in filenames if f.endswith(META_SUFFIX)]
			if not metas:
				# loose PDFs: each a book (the folder's subfolders are looked at too)
				for name in sorted(filenames):
					if (
						name.lower().endswith(".pdf")
						and not name.startswith(".")
						and not name.endswith("_text.pdf")
					):
						yield bare_id(name), os.path.relpath(os.path.join(dirpath, name), self.root)
						seen += 1
						if limit and seen >= limit:
							return
				continue
			folder = os.path.basename(dirpath)
			meta = f"{folder}{META_SUFFIX}" if f"{folder}{META_SUFFIX}" in metas else metas[0]
			identifier = meta[: -len(META_SUFFIX)]
			yield identifier, os.path.relpath(dirpath, self.root)
			dirnames[:] = []  # an item folder's subfolders are not items
			seen += 1
			if limit and seen >= limit:
				return

	def _folder(self, loc: str) -> str:
		return os.path.dirname(loc) if is_bare(loc) else loc

	def list_files(self, loc: str) -> list[str]:
		if is_bare(loc):
			return [os.path.basename(loc)] if os.path.isfile(self._path(loc)) else []
		path = self._path(loc)
		try:
			return sorted(f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
		except FileNotFoundError:
			return []

	def read(self, loc: str, name: str) -> bytes | None:
		try:
			with open(self._path(self._folder(loc), name), "rb") as f:
				return f.read()
		except (FileNotFoundError, IsADirectoryError):
			return None

	def file_path(self, loc: str, name: str) -> str | None:
		path = self._path(self._folder(loc), name)
		return path if os.path.isfile(path) else None

	def load_item(self, identifier: str, loc: str) -> dict:
		if not is_bare(loc):
			return super().load_item(identifier, loc)
		from sok_resdesk.core.pdfrender import pdf_info

		path = self._path(loc)
		if not os.path.isfile(path):
			raise StoreError(f"{loc}: not found")
		name = os.path.basename(loc)
		return {
			"metadata": bare_meta(identifier, name, pdf_info(path)),
			"files": [{"name": name}],
			"page_numbers": None,
		}

	def signature(self, loc: str, identifier: str) -> str:
		if is_bare(loc):
			st = os.stat(self._path(loc))
			return hashlib.sha1(f"{loc}:{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:16]
		parts = []
		for name in self.list_files(loc):
			if name.endswith((META_SUFFIX, ".gz", ".html", ".xml", ".txt", ".pdf")):
				st = os.stat(self._path(loc, name))
				parts.append(f"{name}:{st.st_size}:{int(st.st_mtime)}")
		return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


class _LinkParser(HTMLParser):
	def __init__(self):
		super().__init__()
		self.links: list[str] = []

	def handle_starttag(self, tag, attrs):
		if tag == "a":
			href = dict(attrs).get("href")
			if href:
				self.links.append(href)


class HttpStore(ItemStore):
	kind = "http"

	def __init__(self, base_url: str, manifest_url: str = "", session=None, timeout: int = 60):
		self.base = base_url.rstrip("/") + "/"
		self.manifest_url = manifest_url
		self.session = session or requests.Session()
		self.session.headers.setdefault(
			"User-Agent", "SOK-ResearchDesk/0.11 (+https://github.com/ServantsOfKnowledge/researchdesk)"
		)
		self.timeout = timeout
		self._listing: dict[str, list[str]] = {}

	def _get(self, url: str) -> requests.Response:
		for attempt in range(3):
			try:
				resp = self.session.get(url, timeout=self.timeout)
				if resp.status_code in (429, 502, 503, 504):
					time.sleep(2**attempt)
					continue
				return resp
			except requests.RequestException as exc:
				if attempt == 2:
					raise StoreError(f"{url}: {exc}") from exc
				time.sleep(2**attempt)
		raise StoreError(f"{url}: gave up")

	def _url(self, loc: str, name: str = "") -> str:
		path = "/".join(quote(p) for p in loc.strip("/").split("/") if p)
		url = urljoin(self.base, path + "/")
		return url + quote(name) if name else url

	def _dir_links(self, url: str) -> list[str]:
		resp = self._get(url)
		if resp.status_code != 200:
			return []
		parser = _LinkParser()
		parser.feed(resp.text)
		out = []
		for href in parser.links:
			if href.startswith(("?", "#", "../", "/")) or "://" in href:
				# absolute links: keep only those inside this directory
				if "://" in href or href.startswith("/"):
					full = urljoin(url, href)
					if not full.startswith(url) or full == url:
						continue
					href = full[len(url) :]
				else:
					continue
			out.append(unquote(href))
		return out

	def iter_items(self, limit: int = 0) -> Iterator[tuple[str, str]]:
		seen = 0
		if self.manifest_url:
			resp = self._get(self.manifest_url)
			if resp.status_code != 200:
				raise StoreError(f"manifest {self.manifest_url}: HTTP {resp.status_code}")
			for line in resp.text.splitlines():
				loc = line.strip().strip("/")
				if not loc or loc.startswith("#"):
					continue
				yield loc.split("/")[-1], loc
				seen += 1
				if limit and seen >= limit:
					return
			return
		# crawl directory listings (breadth-first, bounded depth)
		queue = [("", 0)]
		while queue:
			loc, depth = queue.pop(0)
			links = self._dir_links(self._url(loc))
			files = [link for link in links if not link.endswith("/")]
			metas = [f for f in files if f.endswith(META_SUFFIX)]
			if metas:
				self._listing[loc] = files
				folder = loc.split("/")[-1]
				meta = f"{folder}{META_SUFFIX}" if f"{folder}{META_SUFFIX}" in metas else metas[0]
				yield meta[: -len(META_SUFFIX)], loc
				seen += 1
				if limit and seen >= limit:
					return
				continue
			if depth < MAX_SCAN_DEPTH:
				for link in sorted(link for link in links if link.endswith("/")):
					name = link.strip("/")
					if name and not name.startswith("."):
						queue.append((f"{loc}/{name}".strip("/"), depth + 1))

	def list_files(self, loc: str) -> list[str]:
		if loc not in self._listing:
			links = self._dir_links(self._url(loc))
			files = [link for link in links if not link.endswith("/")]
			if not files:
				# no directory listing: probe the conventional IA file names
				ident = loc.split("/")[-1]
				candidates = [
					f"{ident}{s}"
					for s in (
						META_SUFFIX,
						"_hocr_searchtext.txt.gz",
						"_hocr_pageindex.json.gz",
						"_page_numbers.json",
						"_hocr.html",
						"_chocr.html.gz",
						"_djvu.xml",
						"_djvu.txt",
						".pdf",
					)
				] + ["__ia_thumb.jpg"]
				files = [c for c in candidates if self._exists(loc, c)]
			self._listing[loc] = files
		return self._listing[loc]

	def _exists(self, loc: str, name: str) -> bool:
		try:
			resp = self.session.head(self._url(loc, name), timeout=self.timeout, allow_redirects=True)
			return resp.status_code == 200
		except requests.RequestException:
			return False

	def read(self, loc: str, name: str) -> bytes | None:
		resp = self._get(self._url(loc, name))
		return resp.content if resp.status_code == 200 else None

	def public_url(self, loc: str, name: str) -> str | None:
		return self._url(loc, name)

	def signature(self, loc: str, identifier: str) -> str:
		parts = []
		for name in self.list_files(loc):
			if name.endswith((META_SUFFIX, ".gz", ".html", ".xml", ".txt")):
				try:
					resp = self.session.head(self._url(loc, name), timeout=self.timeout, allow_redirects=True)
					parts.append(
						f"{name}:{resp.headers.get('Content-Length', '')}:{resp.headers.get('Last-Modified', resp.headers.get('ETag', ''))}"
					)
				except requests.RequestException:
					parts.append(name)
		return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def open_store(kind: str, location: str, manifest_url: str = "") -> ItemStore:
	if kind == "http" or re.match(r"^https?://", location or ""):
		if not urlparse(location).scheme:
			raise StoreError("Server URL must start with http:// or https://")
		return HttpStore(location, manifest_url)
	return FolderStore(location)
