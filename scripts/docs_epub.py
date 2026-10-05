#!/usr/bin/env python3
"""Make an EPUB of all the documentation (the help pages for readers, staff and administrators).

    python3 scripts/docs_epub.py                          # every page → dist/research-desk-guide.epub
    python3 scripts/docs_epub.py --audience reader        # only the pages for readers
    python3 scripts/docs_epub.py -o guide.epub

Needs the `markdown` package (pip install markdown). The pages come in the order and groups of
the in-app help (sok_resdesk/core/helpdocs.py); links between pages become links inside the book,
the screenshots are packed in, and the contents list follows the groups and each page's headings.
Releases carry it (.github/workflows/release.yml).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import uuid
import zipfile
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import markdown  # noqa: E402

from sok_resdesk.core import helpdocs  # noqa: E402

TITLE = "SOK Research Desk: the guide"
CSS = """
body { font-family: serif; line-height: 1.45; margin: 0 0.6em; }
h1 { font-size: 1.6em; border-bottom: 2px solid #8a1c1c; padding-bottom: .15em; }
h2 { font-size: 1.25em; color: #8a1c1c; margin-top: 1.4em; }
h3 { font-size: 1.05em; }
code { font-family: monospace; font-size: .9em; background: #f3f3f3; }
pre { background: #f6f6f6; border: 1px solid #ddd; padding: .5em; white-space: pre-wrap; font-size: .8em; }
pre code { background: none; }
table { border-collapse: collapse; margin: .8em 0; font-size: .85em; }
th, td { border: 1px solid #bbb; padding: .25em .4em; vertical-align: top; text-align: left; }
th { background: #f0eceb; }
img { max-width: 100%; height: auto; }
.group { text-align: center; margin-top: 30%; }
"""
MEDIA = {
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".svg": "image/svg+xml",
}


def chapter_file(page: helpdocs.Page) -> str:
	return f"{page.slug}.xhtml"


def render(page: helpdocs.Page, images: dict[str, str]) -> tuple[str, list[tuple[int, str, str]]]:
	"""(the page as XHTML body, its (level, text, anchor) headings). Images used go into `images`."""
	md = (ROOT / "docs" / page.file).read_text(encoding="utf-8")

	def page_url(target, anchor):
		return chapter_file(target) + (f"#{anchor}" if anchor else "") if target else None

	md = helpdocs.rewrite(md, page_url, image_url=lambda name: f"images/{name}")
	for name in re.findall(r"\(images/([^)\s]+)", md):
		images[name] = str(ROOT / helpdocs.IMAGE_DIR / name)
	original = (ROOT / "docs" / page.file).read_text(encoding="utf-8")
	body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"], output_format="xhtml")
	body = helpdocs.add_heading_ids(body, original)
	# raw HTML in the docs (a <br> in a table cell) must be well-formed XML
	body = re.sub(r"<(br|hr|img|wbr)(\s[^>]*?)?\s*/?>", lambda m: f"<{m.group(1)}{m.group(2) or ''}/>", body)
	return body, helpdocs.headings(original)


def xhtml(title: str, body: str) -> str:
	return (
		'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
		'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">'
		f'<head><meta charset="utf-8"/><title>{escape(title)}</title>'
		'<link rel="stylesheet" type="text/css" href="style.css"/></head>'
		f"<body>{body}</body></html>"
	)


def build(out: Path, audience: str = "all") -> int:
	pages = [
		p for p in helpdocs.PAGES if audience == "all" or p.audience == audience or p.audience == "reader"
	]
	if audience == "reader":
		pages = [p for p in helpdocs.PAGES if p.audience == "reader"]
	images: dict[str, str] = {}
	chapters: list[tuple[str, str, str]] = []  # (file, title, xhtml)
	toc: list[str] = []
	group = None
	version = (ROOT / "sok_resdesk" / "__init__.py").read_text().split('"')[1]
	today = dt.date.today().isoformat()
	cover = (
		f'<section epub:type="titlepage"><h1>{TITLE}</h1><p>Version {version}, {today}</p>'
		"<p>The help pages for readers, library staff and administrators of "
		'<a href="https://github.com/ServantsOfKnowledge/researchdesk">SOK Research Desk</a>.</p></section>'
	)
	chapters.append(("title.xhtml", TITLE, xhtml(TITLE, cover)))
	toc.append('<li><a href="title.xhtml">Title</a></li>')
	open_group = False
	for page in pages:
		if page.group != group:
			group = page.group
			if open_group:
				toc.append("</ol></li>")
			gfile = f"group-{re.sub('[^a-z]+', '-', group.lower()).strip('-')}.xhtml"
			chapters.append((gfile, group, xhtml(group, f'<h1 class="group">{escape(group)}</h1>')))
			toc.append(f'<li><a href="{gfile}">{escape(group)}</a><ol>')
			open_group = True
		body, heads = render(page, images)
		chapters.append((chapter_file(page), page.title, xhtml(page.title, body)))
		subs = "".join(
			f'<li><a href="{chapter_file(page)}#{a}">{escape(re.sub(r"[`*_]", "", t))}</a></li>'
			for lvl, t, a in heads
			if lvl == 2
		)
		toc.append(
			f'<li><a href="{chapter_file(page)}">{escape(page.title)}</a>'
			+ (f"<ol>{subs}</ol>" if subs else "")
			+ "</li>"
		)
	if open_group:
		toc.append("</ol></li>")
	nav = xhtml(
		"Contents",
		'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "".join(toc) + "</ol></nav>",
	)
	manifest = [
		'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
		'<item id="css" href="style.css" media-type="text/css"/>',
	]
	spine = []
	for n, (f, _t, _x) in enumerate(chapters):
		manifest.append(f'<item id="c{n}" href="{f}" media-type="application/xhtml+xml"/>')
		spine.append(f'<itemref idref="c{n}"/>')
	for n, name in enumerate(sorted(images)):
		media = MEDIA.get(Path(name).suffix.lower(), "application/octet-stream")
		manifest.append(f'<item id="i{n}" href="images/{name}" media-type="{media}"/>')
	opf = (
		'<?xml version="1.0" encoding="utf-8"?>\n'
		'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
		'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
		f'<dc:identifier id="id">urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, "research-desk-guide-" + version)}</dc:identifier>'
		f"<dc:title>{TITLE}</dc:title><dc:language>en</dc:language>"
		"<dc:creator>Servants of Knowledge and contributors</dc:creator>"
		f'<meta property="dcterms:modified">{today}T00:00:00Z</meta>'
		'<meta property="schema:accessMode">textual</meta><meta property="schema:accessMode">visual</meta>'
		'<meta property="schema:accessibilityFeature">tableOfContents</meta>'
		"</metadata><manifest>"
		+ "".join(manifest)
		+ '</manifest><spine><itemref idref="nav"/>'
		+ "".join(spine)
		+ "</spine></package>"
	)
	container = (
		'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
		'<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
	)
	out.parent.mkdir(parents=True, exist_ok=True)
	with zipfile.ZipFile(out, "w") as z:
		z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
		z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
		z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
		z.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
		z.writestr("OEBPS/style.css", CSS, zipfile.ZIP_DEFLATED)
		for f, _t, x in chapters:
			z.writestr(f"OEBPS/{f}", x, zipfile.ZIP_DEFLATED)
		for name, path in images.items():
			if Path(path).is_file():
				z.write(path, f"OEBPS/images/{name}", zipfile.ZIP_DEFLATED)
	return len(pages)


def main() -> None:
	ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	ap.add_argument("-o", "--output", default=str(ROOT / "dist" / "research-desk-guide.epub"))
	ap.add_argument("--audience", choices=["all", "reader", "staff"], default="all")
	args = ap.parse_args()
	n = build(Path(args.output), args.audience)
	print(f"{args.output}: {n} pages")


if __name__ == "__main__":
	main()
