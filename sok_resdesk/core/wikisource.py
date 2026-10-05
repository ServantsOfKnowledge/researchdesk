"""Books from Wikisource (any language's: kn.wikisource.org, sa.wikisource.org, wikisource.org…).

Wikisource keeps a transcription of a scanned book as an **Index** page (the book: title, author,
year, publisher…) and a **Page** for every scanned page (its text, with a proofreading level).
This module reads those through the MediaWiki API; nothing here imports Frappe:

* :class:`WikiClient`: the API, politely (one request at a time, a pause between, a descriptive
  User-Agent), with the API's continuation followed;
* ``parse_index`` / ``parse_page`` / ``plain``: the wikitext of an Index and of a Page turned
  into the book's details and each page's plain text and quality;
* ``item_id_for``, ``image_url``, ``meta``: how a book is named, where its page images are, and
  the archive.org-style metadata the catalogue's clean-up reads.

The text is Wikisource contributors' work under CC BY-SA 4.0; the scan has its own rights
(Commons or the library it came from). The book is catalogued with both said.
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

import requests

USER_AGENT = "SOK-ResearchDesk (+https://github.com/ServantsOfKnowledge/researchdesk; wikisource reader)"
INDEX_NS, PAGE_NS = 252, 250  # Proofread Page's namespaces (canonical names Index and Page)
LICENCE = "https://creativecommons.org/licenses/by-sa/4.0/"
RIGHTS = "Text: Wikisource contributors, CC BY-SA 4.0. The scan has its own rights; see its file page."
# a page's proofreading level (the <pagequality level="…"/> of its wikitext)
QUALITY = {0: "without text", 1: "not proofread", 2: "problematic", 3: "proofread", 4: "validated"}
MIN_LEVEL = {"Any text": 1, "Proofread": 3, "Validated": 4}
PAGE_WIDTH = 1000


class WikiError(Exception):
	pass


# -- the API -----------------------------------------------------------------------------------------


class WikiClient:
	def __init__(self, site: str, delay: float = 0.3, session=None, timeout: int = 60):
		self.site = site.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
		if not re.fullmatch(r"[a-z0-9.-]+\.(wikisource\.org|wikimedia\.org)|wikisource\.org", self.site):
			raise WikiError("Give a Wikisource address such as kn.wikisource.org")
		self.delay = delay
		self.timeout = timeout
		self.session = session or requests.Session()
		self.session.headers["User-Agent"] = USER_AGENT
		self._last = 0.0

	@property
	def api(self) -> str:
		return f"https://{self.site}/w/api.php"

	def get(self, **params) -> dict:
		wait = self.delay - (time.monotonic() - self._last)
		if wait > 0:
			time.sleep(wait)
		params = {"format": "json", "formatversion": 2, **params}
		for attempt in range(4):
			try:
				resp = self.session.get(self.api, params=params, timeout=self.timeout)
				self._last = time.monotonic()
				if resp.status_code in (429, 502, 503, 504):
					time.sleep(2**attempt * 2)
					continue
				if resp.status_code != 200:
					raise WikiError(f"{self.site}: HTTP {resp.status_code}")
				data = resp.json()
				if "error" in data:
					raise WikiError(f"{self.site}: {data['error'].get('info') or data['error'].get('code')}")
				return data
			except (requests.RequestException, ValueError) as e:
				if attempt == 3:
					raise WikiError(f"{self.site}: {e}") from e
				time.sleep(2**attempt)
		raise WikiError(f"{self.site}: gave up after retries")

	def query(self, **params):
		"""Every page of an API query's results (its `continue` followed): yields each response."""
		cont: dict = {}
		while True:
			data = self.get(action="query", **params, **cont)
			yield data
			cont = data.get("continue") or {}
			if not cont:
				return

	# what the site calls its namespaces: Proofread Page's are 252 (Index) and 250 (Page), but a
	# site may differ; its canonical names say
	def namespaces(self) -> tuple[int, int]:
		data = self.get(action="query", meta="siteinfo", siprop="namespaces")
		found = {}
		for ns in (data.get("query", {}).get("namespaces") or {}).values():
			canonical = ns.get("canonical")
			if canonical in ("Index", "Page"):
				found[canonical] = int(ns["id"])
		return found.get("Index", INDEX_NS), found.get("Page", PAGE_NS)

	def indexes_in_category(self, category: str, index_ns: int = INDEX_NS):
		"""Titles of the Index pages in a category (with its subcategories left out)."""
		cat = category if ":" in category else f"Category:{category}"
		for data in self.query(
			list="categorymembers", cmtitle=cat, cmnamespace=index_ns, cmlimit=500, cmtype="page"
		):
			for m in data.get("query", {}).get("categorymembers", []):
				yield m["title"]

	def wikitext(self, title: str) -> str:
		data = self.get(
			action="query", prop="revisions", rvprop="content", rvslots="main", titles=title, redirects=1
		)
		pages = data.get("query", {}).get("pages") or []
		if not pages or pages[0].get("missing"):
			raise WikiError(f"{title} is not on {self.site}")
		return pages[0]["revisions"][0]["slots"]["main"]["content"]

	def file_pages(self, filename: str) -> int:
		"""How many pages the scan (File:X.pdf) has, or 0 when the wiki doesn't say."""
		data = self.get(
			action="query", prop="imageinfo", iiprop="size", titles=f"File:{filename}", redirects=1
		)
		pages = data.get("query", {}).get("pages") or []
		info = (pages[0].get("imageinfo") or [{}])[0] if pages else {}
		return int(info.get("pagecount") or 0)

	def pages(self, filename: str, page_ns: int = PAGE_NS):
		"""Yields {"leaf", "quality", "user", "text"} for every Page of the scan that exists
		(leaf counts from 0; page 1 of the scan is leaf 0), in scan order."""
		got = []
		for data in self.query(
			generator="allpages",
			gapnamespace=page_ns,
			gapprefix=f"{filename}/",
			gaplimit=50,
			prop="revisions",
			rvprop="content",
			rvslots="main",
		):
			for p in data.get("query", {}).get("pages", []):
				number = page_number(p.get("title", ""), filename)
				revs = p.get("revisions") or []
				if number is None or not revs:
					continue
				parsed = parse_page(revs[0]["slots"]["main"]["content"])
				got.append({"leaf": number - 1, **parsed})
		yield from sorted(got, key=lambda p: p["leaf"])


# -- names and addresses -----------------------------------------------------------------------------


def filename_of(index_title: str) -> str:
	"""`Index:Some book.pdf` → `Some book.pdf`."""
	return index_title.split(":", 1)[1].strip() if ":" in index_title else index_title.strip()


def page_number(page_title: str, filename: str) -> int | None:
	"""`Page:Some book.pdf/12` → 12."""
	m = re.search(r"/(\d+)$", page_title)
	return int(m.group(1)) if m and filename_of(page_title).startswith(f"{filename}/") else None


def item_id_for(site: str, index_title: str) -> str:
	"""The book's identifier here: `ws-kn-Some-book.pdf` (language, then the scan's name)."""
	lang = site.split(".")[0] if site.endswith(".wikisource.org") else "ws"
	name = re.sub(r"[^\w.-]+", "-", filename_of(index_title), flags=re.UNICODE).strip("-")
	return f"ws-{lang}-{name}"[:140]


def index_url(site: str, index_title: str) -> str:
	return f"https://{site}/wiki/{quote(index_title.replace(' ', '_'), safe=':/_(),.-')}"


def file_url(site: str, filename: str) -> str:
	"""The scan itself (a PDF or DjVu), as Wikimedia serves it."""
	return f"https://{site}/wiki/Special:Redirect/file/{quote(filename.replace(' ', '_'), safe='_(),.-')}"


def image_url(site: str, filename: str, leaf: int, width: int = PAGE_WIDTH) -> str:
	"""One page of the scan as an image (the wiki draws it from the PDF or DjVu)."""
	return f"{file_url(site, filename)}?page={int(leaf) + 1}&width={int(width)}"


# -- wikitext → text ----------------------------------------------------------------------------------

_NOINCLUDE = re.compile(r"<noinclude>.*?</noinclude>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_REF = re.compile(r"<ref\b[^>]*?/>|<ref\b[^>]*>.*?</ref>", re.S | re.I)
_QUALITY = re.compile(r"<pagequality\b([^>]*)/?>", re.I)
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
# templates that only format their text: the text is kept; any other template is dropped
FORMATTING = {
	"larger", "smaller", "x-larger", "xx-larger", "xxx-larger", "fine", "sc", "asc", "c", "center",
	"centre", "right", "r", "left", "nowrap", "hi", "hanging indent", "float right", "float left",
	"dropinitial", "di", "drop initial", "ditto", "bold", "italic", "u", "uc", "lc", "rule", "block center",
}  # fmt: skip
_TEMPLATE = re.compile(r"\{\{([^{}|]*)((?:\|[^{}]*)?)\}\}")


def _template(m: re.Match) -> str:
	name = re.sub(r"\s+", " ", m.group(1)).strip().lower()
	if name not in FORMATTING:
		return ""
	args = [a for a in m.group(2).split("|")[1:] if "=" not in a.split("[[")[0] or a.startswith("1=")]
	text = args[0] if name in ("hi", "hanging indent") and len(args) > 1 else (args[-1] if args else "")
	return text[2:] if text.startswith("1=") else text


def plain(wikitext: str) -> str:
	"""A page's wikitext as plain text: templates that only format are unwrapped, any other
	dropped; links give their label; bold, italic, tags and notes go. Approximate by design:
	good for finding words and reading, not for typesetting."""
	text = _NOINCLUDE.sub("", wikitext or "")
	text = _COMMENT.sub("", text)
	text = _REF.sub("", text)
	for _ in range(8):  # innermost templates first
		new = _TEMPLATE.sub(_template, text)
		if new == text:
			break
		text = new
	text = re.sub(
		r"\{\|.*?\|\}", lambda m: re.sub(r"^[|!+-].*?\|", "", m.group(0), flags=re.M), text, flags=re.S
	)
	text = re.sub(r"\[\[(?:File|Image|Category|[a-z]{2}):[^\]]*\]\]", "", text, flags=re.I)
	text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
	text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
	text = re.sub(r"\[(?:https?:)?//\S+\s+([^\]]+)\]", r"\1", text)
	text = re.sub(r"'{2,5}", "", text)
	text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
	text = re.sub(
		r"</?(?:poem|div|span|small|big|sup|sub|center|section|pages|templatestyles)[^>]*>",
		"",
		text,
		flags=re.I,
	)
	text = re.sub(r"<[^>]+>", "", text)
	text = re.sub(r"[ \t]+\n", "\n", text)
	return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_page(wikitext: str) -> dict:
	"""{"quality": 0–4, "user": who proofread or validated it, "text": plain text}."""
	m = _QUALITY.search(wikitext or "")
	attrs = dict(_ATTR.findall(m.group(1))) if m else {}
	try:
		level = int(attrs.get("level", 0))
	except ValueError:
		level = 0
	body = re.sub(r"<noinclude>.*?</noinclude>", "", wikitext or "", flags=re.S | re.I)
	return {"quality": min(max(level, 0), 4), "user": attrs.get("user", ""), "text": plain(body)}


# -- the Index page ----------------------------------------------------------------------------------

_ARG = re.compile(r"^\|\s*([A-Za-z_]+)\s*=(.*?)(?=^\|\s*[A-Za-z_]+\s*=|^\}\}|\Z)", re.S | re.M)


def parse_index(wikitext: str) -> dict:
	"""The Index template's fields (Title, Author, Language, Publisher, Address, Year, Source,
	Remarks…) as plain strings, keys lower-cased; links and markup removed."""
	fields = {}
	for key, value in _ARG.findall(wikitext or ""):
		value = plain(value)
		if value:
			fields[key.strip().lower()] = value
	return fields


def meta(fields: dict, *, site: str, index_title: str, pages: int, scan: str) -> dict:
	"""The archive.org-style metadata the catalogue normalises, from an Index's fields."""
	filename = filename_of(index_title)
	title = fields.get("title") or re.sub(r"\.(pdf|djvu)$", "", filename, flags=re.I)
	authors = [a.strip() for a in re.split(r"\s*[;&]\s*|\s+and\s+", fields.get("author", "")) if a.strip()]
	out = {
		"title": [title],
		"creator": authors,
		"publisher": [fields["publisher"]] if fields.get("publisher") else [],
		"date": fields.get("year", ""),
		"language": [fields["language"]] if fields.get("language") else [site.split(".")[0]],
		"description": [fields["remarks"]] if fields.get("remarks") else [],
		"collection": [f"Wikisource ({site})"],
		"licenseurl": LICENCE,
		"rights": RIGHTS,
	}
	if scan:
		out["scan"] = scan
	return {k: v for k, v in out.items() if v}
