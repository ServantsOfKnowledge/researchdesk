"""A book's text as an accessible EPUB 3 or plain text, for screen readers, braille displays,
large print and reading apps. Pure Python.

The EPUB follows EPUB 3.3 and the EPUB Accessibility 1.1 metadata: the language of the text,
the printed page numbers (a page list and page breaks, so "go to page 52" works and citations
match the printed book), a table of contents, and schema.org accessibility metadata saying the
book is text only and how reliable that text is (OCR, proofread or validated pages). No claim
of conformance is made: OCR text can have errors a person hasn't checked.
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from datetime import UTC, datetime

PAGES_PER_FILE = 50
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _x(s) -> str:
	"""Text for XHTML/XML: escaped, without control characters XML can't hold."""
	return html.escape(_CTRL.sub("", str(s or "")), quote=True)


def page_name(page: dict) -> str:
	"""How the page is called: its printed number, else its place among the images."""
	label = str(page.get("label") or "").strip()
	return label or f"[{int(page['leaf']) + 1}]"


def _paragraphs(text: str) -> str:
	"""A page's text as paragraphs; line breaks inside a paragraph are kept (verse, lists)."""
	out = []
	for block in re.split(r"\n\s*\n", (text or "").strip()):
		lines = [_x(line.strip()) for line in block.splitlines() if line.strip()]
		if lines:
			out.append("<p>" + "<br/>".join(lines) + "</p>")
	return "\n".join(out)


def text_pages(pages: list[dict]) -> list[dict]:
	"""The pages that have text, in order."""
	return [p for p in sorted(pages, key=lambda p: int(p["leaf"])) if (p.get("text") or "").strip()]


def reliability(pages: list[dict]) -> dict:
	"""How many of the pages a person read: {pages, proofread, validated}."""
	have = text_pages(pages)
	validated = sum(1 for p in have if p.get("status") == "Validated")
	proofread = sum(1 for p in have if p.get("status") in ("Proofread", "Validated"))
	return {"pages": len(have), "proofread": proofread, "validated": validated}


def summary(record: dict, pages: list[dict]) -> str:
	"""The accessibility summary: what the file is, and how far the text can be trusted."""
	r = reliability(pages)
	if r["pages"] and r["proofread"] == r["pages"]:
		trust = "Every page was proofread by a person"
		if r["validated"] == r["pages"]:
			trust += " and checked by a second person"
		trust += "."
	elif r["proofread"]:
		trust = (
			f"{r['proofread']} of {r['pages']} pages were proofread by a person; the others are "
			"machine-read (OCR) text and may have errors."
		)
	else:
		trust = "The text is machine-read (OCR) from the scanned pages and may have errors."
	return (
		"The text of a digitised book, with the printed page numbers. It has no images: the "
		f"scanned pages are on the library's website. {trust}"
	)


def plain_text(record: dict, pages: list[dict], url: str = "") -> str:
	"""The book's text in one plain-text file, each page headed by its number."""
	head = [record.get("title") or record.get("item_id") or ""]
	if record.get("creators"):
		head.append("; ".join(record["creators"]))
	if record.get("year"):
		head.append(str(record["year"]))
	if url:
		head.append(url)
	head.append(summary(record, pages))
	out = ["\n".join(head), ""]
	for p in text_pages(pages):
		out.append(f"--- {page_name(p)} ---")
		out.append(_CTRL.sub("", (p.get("text") or "").strip()))
		out.append("")
	return "\n".join(out).rstrip() + "\n"


def _xhtml(title: str, lang: str, body: str) -> str:
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
		f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{_x(lang)}" xml:lang="{_x(lang)}">\n'
		f'<head><meta charset="UTF-8"/><title>{_x(title)}</title><link rel="stylesheet" href="book.css"/></head>\n'
		f"<body>\n{body}\n</body>\n</html>\n"
	)


CSS = """body { line-height: 1.6; }
p { margin: 0 0 1em; }
.pb { display: block; margin: 1.5em 0 .5em; font-size: .8em; color: #555; border-top: 1px solid #ccc; }
.title-page h1 { font-size: 1.6em; }
"""


def build(
	record: dict,
	pages: list[dict],
	lang: str = "",
	url: str = "",
	publisher: str = "",
	modified: datetime | None = None,
) -> bytes:
	"""The EPUB file. `record` is the catalogue record (title, creators, year, item_id, description,
	rights/licence_url), `pages` the page texts ({leaf, label, text, status}), `lang` the text's
	BCP 47 tag, `url` the book's page on the portal."""
	title = record.get("title") or record.get("item_id") or "Untitled"
	lang = lang or "und"
	item_id = record.get("item_id") or "book"
	identifier = url or f"urn:resdesk:{item_id}"
	modified = (modified or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
	have = text_pages(pages)
	chunks = [have[i : i + PAGES_PER_FILE] for i in range(0, len(have), PAGES_PER_FILE)] or [[]]

	files: dict[str, str] = {}
	# the title page
	about = [f"<h1>{_x(title)}</h1>"]
	if record.get("alt_title") and record["alt_title"] != title:
		about.append(f"<p>{_x(record['alt_title'])}</p>")
	if record.get("creators"):
		about.append(f"<p>{_x('; '.join(record['creators']))}</p>")
	facts = ", ".join(_x(v) for v in (record.get("publisher"), record.get("year")) if v)
	if facts:
		about.append(f"<p>{facts}</p>")
	about.append(f"<p>{_x(summary(record, pages))}</p>")
	if url:
		about.append(f'<p>Scanned pages and citations: <a href="{_x(url)}">{_x(url)}</a></p>')
	if record.get("licence_url") or record.get("rights"):
		rights = record.get("licence_url") or record.get("rights")
		about.append(f"<p>Rights: {_x(rights)}</p>")
	files["title.xhtml"] = _xhtml(
		title, lang, '<section class="title-page" epub:type="titlepage">' + "\n".join(about) + "</section>"
	)

	page_list, toc = [], []
	for n, chunk in enumerate(chunks, 1):
		name = f"text-{n:03d}.xhtml"
		body = []
		for p in chunk:
			pid = f"page-{int(p['leaf'])}"
			label = page_name(p)
			body.append(
				f'<span class="pb" epub:type="pagebreak" role="doc-pagebreak" id="{pid}" aria-label="{_x(label)}">{_x(label)}</span>'
			)
			body.append(_paragraphs(p.get("text") or ""))
			page_list.append(f'<li><a href="{name}#{pid}">{_x(label)}</a></li>')
		heading = f"Pages {_x(page_name(chunk[0]))}–{_x(page_name(chunk[-1]))}" if chunk else "No text yet"
		files[name] = _xhtml(
			heading,
			lang,
			f'<section epub:type="bodymatter"><h2>{heading}</h2>\n' + "\n".join(body) + "</section>",
		)
		toc.append(f'<li><a href="{name}">{heading}</a></li>')

	nav = (
		f'<nav epub:type="toc" id="toc" role="doc-toc"><h1>Contents</h1><ol><li><a href="title.xhtml">{_x(title)}</a></li>'
		+ "".join(toc)
		+ "</ol></nav>\n"
		+ (
			'<nav epub:type="page-list" id="page-list" role="doc-pagelist" hidden="hidden"><h1>Pages</h1><ol>'
			+ "".join(page_list)
			+ "</ol></nav>\n"
			if page_list
			else ""
		)
		+ '<nav epub:type="landmarks" id="landmarks" hidden="hidden"><h1>Landmarks</h1><ol>'
		+ '<li><a epub:type="titlepage" href="title.xhtml">Title page</a></li>'
		+ (
			f'<li><a epub:type="bodymatter" href="{next(iter(n for n in files if n.startswith("text-")))}">Text</a></li>'
		)
		+ "</ol></nav>"
	)
	files["nav.xhtml"] = _xhtml(title, lang, nav)

	creators = "".join(
		f'<dc:creator id="creator{i}">{_x(c)}</dc:creator>'
		for i, c in enumerate(record.get("creators") or [], 1)
		if c
	)
	features = ["readingOrder", "structuralNavigation", "tableOfContents", "displayTransformability"]
	if page_list:
		features.append("printPageNumbers")
	meta = [
		f'<dc:identifier id="pub-id">{_x(identifier)}</dc:identifier>',
		f"<dc:title>{_x(title)}</dc:title>",
		creators,
		f"<dc:language>{_x(lang)}</dc:language>",
		f'<meta property="dcterms:modified">{modified}</meta>',
		f"<dc:publisher>{_x(publisher)}</dc:publisher>" if publisher else "",
		f"<dc:date>{_x(record.get('year'))}</dc:date>" if record.get("year") else "",
		f"<dc:source>https://archive.org/details/{_x(item_id)}</dc:source>"
		if record.get("on_archive_org", True) and record.get("source") in (None, "", "Internet Archive")
		else "",
		f"<dc:rights>{_x(record.get('licence_url') or record.get('rights'))}</dc:rights>"
		if record.get("licence_url") or record.get("rights")
		else "",
		f"<dc:description>{_x((record.get('description') or '')[:2000])}</dc:description>"
		if record.get("description")
		else "",
		'<meta property="schema:accessMode">textual</meta>',
		'<meta property="schema:accessModeSufficient">textual</meta>',
		*[f'<meta property="schema:accessibilityFeature">{f}</meta>' for f in features],
		'<meta property="schema:accessibilityHazard">none</meta>',
		f'<meta property="schema:accessibilitySummary">{_x(summary(record, pages))}</meta>',
	]
	if page_list:
		meta.append(f'<meta property="pageBreakSource">{_x(url or identifier)}</meta>')
	items = [
		'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
		'<item id="css" href="book.css" media-type="text/css"/>',
		'<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
		*[
			f'<item id="{n.removesuffix(".xhtml")}" href="{n}" media-type="application/xhtml+xml"/>'
			for n in files
			if n.startswith("text-")
		],
	]
	spine = [
		'<itemref idref="title"/>',
		*[f'<itemref idref="{n.removesuffix(".xhtml")}"/>' for n in files if n.startswith("text-")],
	]
	opf = (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="{_x(lang)}" '
		'prefix="schema: http://schema.org/ a11y: http://www.idpf.org/epub/vocab/package/a11y/#">\n'
		'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
		+ "\n".join(m for m in meta if m)
		+ "\n</metadata>\n<manifest>\n"
		+ "\n".join(items)
		+ "\n</manifest>\n<spine>\n"
		+ "\n".join(spine)
		+ "\n</spine>\n</package>\n"
	)
	container = (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
		'<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles>'
		"</container>\n"
	)
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as z:
		z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
		z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
		z.writestr("EPUB/package.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
		z.writestr("EPUB/book.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
		for name, text in files.items():
			z.writestr(f"EPUB/{name}", text, compress_type=zipfile.ZIP_DEFLATED)
	return buf.getvalue()
