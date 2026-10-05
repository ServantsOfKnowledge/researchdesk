"""Plain text from an EPUB (or a plain text / HTML file), so books in a Calibre library can be
searched like the rest. Pure Python (no Frappe), so it is unit-tested directly.

An EPUB is a zip: ``META-INF/container.xml`` names the package (OPF), whose *spine* gives the
reading order of the XHTML documents. Each is reduced to its text, in that order.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

MAX_CHARS = 20_000_000  # text kept for one book
MAX_MEMBER = 30_000_000  # the biggest document read out of the zip (zip bombs)
BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "blockquote", "pre"}
SKIP = {"script", "style", "head", "title"}


class _Text(HTMLParser):
	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.out: list[str] = []
		self.skip = 0

	def handle_starttag(self, tag, attrs):
		if tag in SKIP:
			self.skip += 1
		elif tag in BLOCKS:
			self.out.append("\n")

	def handle_endtag(self, tag):
		if tag in SKIP:
			self.skip = max(0, self.skip - 1)
		elif tag in BLOCKS:
			self.out.append("\n")

	def handle_data(self, data):
		if not self.skip:
			self.out.append(data)


def html_text(markup: str) -> str:
	"""The words of an (X)HTML document: blocks on their own lines, scripts and styles dropped."""
	p = _Text()
	p.feed(markup)
	text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
	return re.sub(r"\n\s*\n+", "\n\n", re.sub(r" ?\n ?", "\n", text)).strip()


def _decode(raw: bytes) -> str:
	for enc in ("utf-8", "utf-16"):
		try:
			return raw.decode(enc)
		except UnicodeDecodeError:
			continue
	return raw.decode("latin-1", errors="replace")


def _local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1]


def spine_files(z: zipfile.ZipFile) -> list[str]:
	"""The XHTML documents in reading order (paths inside the zip)."""
	container = ET.fromstring(z.read("META-INF/container.xml"))
	opf = next((e.get("full-path") for e in container.iter() if _local(e.tag) == "rootfile"), "")
	if not opf:
		return []
	root = ET.fromstring(z.read(opf))
	manifest = {e.get("id"): e.get("href") for e in root.iter() if _local(e.tag) == "item"}
	base = posixpath.dirname(opf)
	order = [e.get("idref") for e in root.iter() if _local(e.tag) == "itemref"]
	names = set(z.namelist())
	out = []
	for ref in order:
		href = manifest.get(ref)
		if not href:
			continue
		path = posixpath.normpath(posixpath.join(base, href.split("#")[0]))
		if path in names and path.rsplit(".", 1)[-1].lower() in ("xhtml", "html", "htm", "xml"):
			out.append(path)
	return out


def epub_text(path: str) -> str:
	"""A book's text from its EPUB, chapter after chapter ('' when it is not a readable EPUB)."""
	try:
		with zipfile.ZipFile(path) as z:
			parts, total = [], 0
			for name in spine_files(z):
				if z.getinfo(name).file_size > MAX_MEMBER:
					continue
				text = html_text(_decode(z.read(name)))
				if text:
					parts.append(text)
					total += len(text)
				if total > MAX_CHARS:
					break
			return "\n\n".join(parts)[:MAX_CHARS]
	except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
		return ""


def file_text(path: str) -> str:
	"""Text of a book file: an EPUB, or a plain text or HTML file ('' for anything else)."""
	ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
	if ext == "epub":
		return epub_text(path)
	if ext in ("txt", "text"):
		with open(path, "rb") as f:
			return _decode(f.read(MAX_CHARS))
	if ext in ("html", "htm", "xhtml"):
		with open(path, "rb") as f:
			return html_text(_decode(f.read(MAX_CHARS)))
	return ""
