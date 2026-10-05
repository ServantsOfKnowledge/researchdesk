"""OPDS 1.2 (Atom) catalogue feeds, so e-reader apps (KOReader, Moon+ Reader, Thorium, Aldiko…)
can browse the library and download its books. Pure Python (no Frappe), so it is unit-tested directly.

A *navigation* feed lists other feeds (the newest books, the collections); an *acquisition* feed
lists books, each with a link per file a reader may download.
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

NAV = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ = "application/atom+xml;profile=opds-catalog;kind=acquisition"
MIMES = {
	"pdf": "application/pdf",
	"epub": "application/epub+zip",
	"mobi": "application/x-mobipocket-ebook",
	"azw3": "application/vnd.amazon.ebook",
	"djvu": "image/vnd.djvu",
	"txt": "text/plain",
	"cbz": "application/vnd.comicbook+zip",
	"jpg": "image/jpeg",
	"jpeg": "image/jpeg",
	"png": "image/png",
	"mp3": "audio/mpeg",
	"mp4": "video/mp4",
}
PER_PAGE = 50


def mime_of(name: str) -> str:
	return (
		MIMES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
		if "." in name
		else "application/octet-stream"
	)


def _attrs(**kw) -> str:
	return " ".join(f"{k.rstrip('_')}={quoteattr(str(v))}" for k, v in kw.items() if v not in (None, ""))


def link(rel: str, href: str, type_: str = "", title: str = "") -> str:
	return f"<link {_attrs(rel=rel, href=href, type_=type_, title=title)}/>"


def _id(base: str, kind: str, name: str = "") -> str:
	return f"urn:resdesk:{quote(base, safe='')}:{kind}" + (f":{quote(name, safe='')}" if name else "")


def entry(base: str, book: dict) -> str:
	"""One book. book: item_id, title, authors [str], language, summary, updated, year, cover (url),
	files [(url, name)] a reader may download, subjects [str]."""
	i = book["item_id"]
	parts = [
		"<entry>",
		f"<title>{escape(book.get('title') or i)}</title>",
		f"<id>{escape(_id(base, 'item', i))}</id>",
		f"<updated>{escape(book.get('updated') or '1970-01-01T00:00:00Z')}</updated>",
	]
	for a in book.get("authors") or []:
		parts.append(f"<author><name>{escape(a)}</name></author>")
	if book.get("language"):
		parts.append(f"<dc:language>{escape(book['language'])}</dc:language>")
	if book.get("year"):
		parts.append(f"<dc:issued>{escape(str(book['year']))}</dc:issued>")
	for s in (book.get("subjects") or [])[:12]:
		parts.append(f"<category term={quoteattr(s)} label={quoteattr(s)}/>")
	if book.get("summary"):
		parts.append(f'<summary type="text">{escape(book["summary"][:1000])}</summary>')
	if book.get("cover"):
		parts.append(link("http://opds-spec.org/image", book["cover"], mime_of(book["cover"].split("?")[0])))
		parts.append(
			link("http://opds-spec.org/image/thumbnail", book["cover"], mime_of(book["cover"].split("?")[0]))
		)
	for url, name in book.get("files") or []:
		parts.append(link("http://opds-spec.org/acquisition/open-access", url, mime_of(name)))
	parts.append(link("alternate", f"{base}/library/item/{quote(i, safe='')}", "text/html"))
	parts.append("</entry>")
	return "\n".join(parts)


def feed(
	base: str,
	*,
	title: str,
	path: str,
	kind: str,
	updated: str,
	entries: list[str],
	nxt: str = "",
	search: bool = True,
) -> str:
	"""A feed document. path: its own address under the portal (e.g. /opds/new?page=2)."""
	self_type = NAV if kind == "nav" else ACQ
	head = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/"'
		' xmlns:opds="http://opds-spec.org/2010/catalog" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">',
		f"<id>{escape(_id(base, 'feed', path))}</id>",
		f"<title>{escape(title)}</title>",
		f"<updated>{escape(updated)}</updated>",
		link("self", base + path, self_type),
		link("start", base + "/opds", NAV),
	]
	if search:
		head.append(link("search", base + "/opds/opensearch.xml", "application/opensearchdescription+xml"))
	if nxt:
		head.append(link("next", base + nxt, ACQ))
	return "\n".join([*head, *entries, "</feed>\n"])


def nav_entry(
	base: str, title: str, path: str, summary: str = "", kind: str = "acq", updated: str = ""
) -> str:
	return "\n".join(
		[
			"<entry>",
			f"<title>{escape(title)}</title>",
			f"<id>{escape(_id(base, 'nav', path))}</id>",
			f"<updated>{escape(updated or '1970-01-01T00:00:00Z')}</updated>",
			(f'<content type="text">{escape(summary)}</content>' if summary else ""),
			link(
				"subsection" if kind == "nav" else "http://opds-spec.org/sort/new",
				base + path,
				NAV if kind == "nav" else ACQ,
			),
			"</entry>",
		]
	)


def opensearch(base: str, title: str) -> str:
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		'<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n'
		f"<ShortName>{escape(title[:16])}</ShortName>\n"
		f"<Description>{escape(title)}</Description>\n"
		f'<Url type="{ACQ}" template="{escape(base)}/opds/search?q={{searchTerms}}"/>\n'
		"</OpenSearchDescription>\n"
	)
