#!/usr/bin/env python3
"""Draw the "How it fits together" picture for the README (sok_resdesk/public/images/how-it-fits.svg).

    python3 scripts/gen_overview.py

Plain SVG with its own background, so it reads the same in GitHub's light and dark themes.
"""

from __future__ import annotations

import base64
import io
from html import escape
from pathlib import Path

IMAGES = Path(__file__).resolve().parents[1] / "sok_resdesk" / "public" / "images"
OUT = IMAGES / "how-it-fits.svg"
W, H = 1200, 760
INK, MUTED, LINE, BG = "#1f272e", "#5b6670", "#9aa7b2", "#ffffff"
GREEN, BLUE, AMBER, PLUM, SLATE = "#2f6f5e", "#2b5f9e", "#a8650c", "#7a3e8f", "#3d4852"

parts: list[str] = []


def box(x, y, w, h, title, lines=(), colour=SLATE, fill="#f6f8fa", bold=True):
	parts.append(
		f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{colour}" stroke-width="1.6"/>'
	)
	parts.append(
		f'<text x="{x + 14}" y="{y + 25}" font-size="15" font-weight="{700 if bold else 500}" fill="{colour}">{escape(title)}</text>'
	)
	for i, line in enumerate(lines):
		parts.append(
			f'<text x="{x + 14}" y="{y + 46 + i * 18}" font-size="12.5" fill="{INK}">{escape(line)}</text>'
		)


def heading(x, text):
	parts.append(
		f'<text x="{x}" y="46" font-size="13" font-weight="700" letter-spacing="1.4" fill="{MUTED}">{escape(text)}</text>'
	)


def arrow(x1, y1, x2, y2, colour=LINE):
	parts.append(
		f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{colour}" stroke-width="2" fill="none" marker-end="url(#a)"/>'
	)


parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')


def logo(x, y, size):
	"""The Servants of Knowledge logo, small and inside the file (GitHub shows no outside pictures in an SVG)."""
	from PIL import Image

	im = Image.open(IMAGES / "sok-logo.png").convert("RGBA").resize((size * 3, size * 3), Image.LANCZOS)
	buf = io.BytesIO()
	im.save(buf, "PNG", optimize=True)
	data = base64.b64encode(buf.getvalue()).decode()
	parts.append(
		f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="data:image/png;base64,{data}" '
		'role="img" aria-label="Servants of Knowledge"/>'
	)


logo(W - 30 - 52, 0, 52)
parts.append(
	f'<text x="30" y="30" font-size="20" font-weight="700" fill="{INK}">SOK Research Desk: how it fits together</text>'
)
heading(30, "BOOKS AND MATERIAL IN")
heading(330, "WORK ON THEM")
heading(640, "KEPT AND FOUND")
heading(910, "OUT")

# column 1: sources
src = [
	("archive.org", "collections, searches, items"),
	("Your folders and servers", "books, leaf images, photographs,"),
	("A Calibre library", "read in place"),
	("Repositories", "DSpace, EPrints, any OAI-PMH"),
	("Wikisource", "books with proofread pages"),
	("Deposits", "people's own work, reviewed"),
]
y = 62
for t, sub in src:
	h = 62 if t != "Your folders and servers" else 80
	lines = (sub,) if t != "Your folders and servers" else (sub, "recordings, PDFs")
	box(30, y, 250, h, t, lines, colour=BLUE)
	y += h + 14

# column 2: work
box(
	330,
	62,
	260,
	112,
	"Ingest jobs",
	("metadata first, page text after", "daily sync: new, changed, removed", "scanned pages read with OCR"),
	colour=GREEN,
)
box(
	330,
	190,
	260,
	112,
	"Proofreading and re-OCR",
	("Tesseract by zone, several languages", "second person validates", "every version kept"),
	colour=GREEN,
)
box(
	330,
	318,
	260,
	96,
	"Machine drafts",
	("speech to text (Whisper)", "handwriting (Kraken)", "people correct them"),
	colour=GREEN,
)
box(
	330,
	430,
	260,
	112,
	"Preservation",
	("OCFL copies, SHA-256 fixity checks", "second copy: folder or S3, repaired", "BagIt exports"),
	colour=AMBER,
)
box(
	330,
	558,
	260,
	96,
	"Review and authorities",
	("review queue of odd records", "Wikidata, VIAF, LCSH matches"),
	colour=PLUM,
)

# column 3: stores
box(
	640,
	62,
	240,
	190,
	"Frappe + MariaDB",
	(
		"the catalogue: books, collections,",
		"page text versions, notes,",
		"archival units, profiles,",
		"accounts and roles",
		"Desk: one sidebar, Server page,",
		"Connections",
	),
	colour=SLATE,
	fill="#eef3f1",
)
box(
	640,
	280,
	240,
	92,
	"Meilisearch",
	("books and every page's text", "Latin letters find Indic script"),
	colour=SLATE,
	fill="#eef3f1",
)
box(
	640,
	400,
	240,
	100,
	"Web and API",
	("portal, Page & text reader", "citations (BibTeX, RIS, CSL…)", "notes, My list, About me"),
	colour=SLATE,
	fill="#eef3f1",
)

# column 4: out
box(
	910,
	62,
	260,
	110,
	"Readers",
	("search, read, cite, browse archives", "type in their own language", "notes, proofreading, deposit"),
	colour=BLUE,
	fill="#eef3fb",
)
box(
	910,
	188,
	260,
	120,
	"Open standards",
	(
		"OAI-PMH · SRU · IIIF · OPDS",
		"COUNTER usage reports",
		"Zotero/Scholar tags, JSON-LD",
		"Koha, VuFind, aggregators",
	),
	colour=BLUE,
	fill="#eef3fb",
)
box(
	910,
	324,
	260,
	112,
	"Giving back",
	("Wikidata, Wikisource, Commons", "(each person's own account)", "archive.org, Koha, webhooks"),
	colour=PLUM,
	fill="#f6eef9",
)
box(
	910,
	452,
	260,
	112,
	"Taking the library away",
	("offline copy for Kiwix (ZIM), zip", "Calibre library", "the guide as an EPUB and PDF"),
	colour=AMBER,
	fill="#fbf3e8",
)

# bottom strip
parts.append(
	f'<rect x="30" y="680" width="1140" height="60" rx="10" fill="#f6f8fa" stroke="{LINE}" stroke-width="1.4"/>'
)
parts.append(
	f'<text x="46" y="706" font-size="14" font-weight="700" fill="{SLATE}">Looking after it (Desk → Server, Connections, Background Jobs)</text>'
)
parts.append(
	f'<text x="46" y="727" font-size="12.5" fill="{INK}">health checks, backups and alerts · gentle upgrades through the optional updater helper · Log QA · search queue care · outgoing email for sign-in</text>'
)


# arrows: each column feeds the next along a shared line, so nothing crosses
def line(x1, y1, x2, y2):
	parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{LINE}" stroke-width="2" fill="none"/>')


def bus(x_from, x_bus, ys, x_to, y_in):
	for y in ys:
		line(x_from, y, x_bus, y)
	line(x_bus, min(ys + [y_in]), x_bus, max(ys + [y_in]))
	arrow(x_bus, y_in, x_to, y_in)


bus(280, 305, [93, 178, 262, 346, 430, 514], 330, 118)  # sources → ingest jobs
bus(590, 615, [246, 366, 486, 606], 640, 160)  # the work on them → the catalogue
arrow(590, 118, 640, 118)  # ingest → the catalogue
arrow(760, 252, 760, 280)  # the catalogue → the search engine
arrow(760, 372, 760, 400)  # the search engine → web and API
# the catalogue, search and web → everything that goes out
for y in (150, 450):
	line(880, y, 895, y)
line(895, 117, 895, 508)
for y in (117, 248, 380, 508):
	arrow(895, y, 910, y)

svg = (
	f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
	'aria-labelledby="t d" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">'
	'<title id="t">SOK Research Desk: how it fits together</title>'
	'<desc id="d">Books and material come in from archive.org, folders, Calibre, repositories, Wikisource and deposits. '
	"Ingest jobs, proofreading, machine drafts, preservation and review work on them. They are kept in Frappe and MariaDB "
	"and found through Meilisearch, and go out to readers, open standards, Wikimedia and other systems, and offline copies.</desc>"
	f'<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{LINE}"/></marker></defs>'
	+ "".join(parts)
	+ "</svg>\n"
)
OUT.write_text(svg, encoding="utf-8")
print(OUT)
