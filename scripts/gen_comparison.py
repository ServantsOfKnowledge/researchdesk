#!/usr/bin/env python3
"""Draw the "Where it fits" comparison of docs/architecture.md (sok_resdesk/public/images/where-it-fits.svg).

    python3 scripts/gen_comparison.py

Plain SVG with its own background, so it reads the same in GitHub's light and dark themes. The rows
repeat the table in docs/architecture.md ("Where it fits in the library and archive ecosystem").
"""

from __future__ import annotations

import textwrap
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sok_resdesk" / "public" / "images" / "where-it-fits.svg"
W = 1200
INK, MUTED, LINE, BG = "#1f272e", "#5b6670", "#d5dce2", "#ffffff"
GREEN, BLUE, AMBER, PLUM, SLATE = "#2f6f5e", "#2b5f9e", "#a8650c", "#7a3e8f", "#3d4852"
# what Research Desk does for each layer -> colour
KINDS = {
	"Replaces": GREEN,
	"Replaces for small institutions": GREEN,
	"Includes": BLUE,
	"Includes the essentials": BLUE,
	"Complements": AMBER,
	"Feeds": PLUM,
}
ROWS = [
	(
		"Digital library / repository",
		"Greenstone, Omeka, CONTENTdm, DSpace, EPrints",
		"Replaces",
		"Catalogue, portal, collections and OAI-PMH in one install",
	),
	(
		"Search and discovery",
		"VuFind, Blacklight",
		"Replaces",
		"Full-text search in Indic scripts and in Latin letters, facets",
	),
	(
		"Reader",
		"Internet Archive BookReader, Mirador, Universal Viewer",
		"Includes",
		"Page image beside its text, citations, notes; every book is a IIIF manifest",
	),
	(
		"OCR and proofreading",
		"Tesseract scripts, FromThePage, Wikisource-style projects",
		"Replaces",
		"OCR on ingest, re-OCR by zones, proofreading, ground truth",
	),
	(
		"Preservation",
		"Archivematica, Preservica, LOCKSS",
		"Replaces for small institutions",
		"Fixity, OCFL, BagIt, a second copy, ARKs. Not a full OAIS",
	),
	(
		"Library system (ILS)",
		"Koha, Evergreen, SOUL, e-Granthalaya",
		"Complements",
		"Links the catalogue to the digital copies and sends the links back",
	),
	(
		"Aggregators",
		"NDLI, Europeana, DPLA, Wikidata, Wikimedia Commons, Wikisource, Internet Archive",
		"Feeds",
		"OAI-PMH, OPDS, IIIF, Wikidata links, archive.org",
	),
	(
		"Digitisation workflow",
		"Goobi, Kitodo, Scribe",
		"Includes the essentials",
		"TTScribe scanning hardware and Repub processing (Servants of Knowledge)",
	),
	(
		"Archival description",
		"AtoM, ArchivesSpace",
		"Includes the essentials",
		"Fonds to item (ISAD(G)), EAD3 export. Not authority records",
	),
	(
		"Institutional repository",
		"DSpace or EPrints for theses and papers",
		"Includes the essentials",
		"Deposit with review, licences, embargoes. Not multi-step workflows",
	),
]
X_LAYER, X_TOOLS, X_KIND, X_WHY = 32, 235, 540, 830
ROW_H, TOP = 54, 118
H = TOP + ROW_H * len(ROWS) + 64


def wrap(text: str, chars: int) -> list[str]:
	return textwrap.wrap(text, chars) or [""]


def main() -> None:
	p = [
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
		'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
		'aria-label="Where SOK Research Desk fits: for each layer of a digital library, the usual tools and '
		'whether Research Desk replaces, includes, complements or feeds them">',
		f'<rect width="{W}" height="{H}" fill="{BG}"/>',
		f'<text x="32" y="46" font-size="24" font-weight="700" fill="{INK}">Where SOK Research Desk fits</text>',
		f'<text x="32" y="72" font-size="14" fill="{MUTED}">One install in place of the four or five systems a digital library '
		"needs, beside the library system you already run</text>",
	]
	heads = [
		(X_LAYER, "LAYER"),
		(X_TOOLS, "TYPICAL TOOLS"),
		(X_KIND, "RESEARCH DESK"),
		(X_WHY, "WHAT IT DOES"),
	]
	for x, label in heads:
		p.append(
			f'<text x="{x}" y="{TOP - 14}" font-size="12" font-weight="700" letter-spacing="1.4" fill="{MUTED}">{label}</text>'
		)
	p.append(f'<line x1="24" y1="{TOP - 4}" x2="{W - 24}" y2="{TOP - 4}" stroke="{INK}" stroke-width="1.5"/>')
	for i, (layer, tools, kind, why) in enumerate(ROWS):
		y = TOP + i * ROW_H
		if i % 2:
			p.append(f'<rect x="24" y="{y}" width="{W - 48}" height="{ROW_H}" fill="#f6f8fa"/>')
		mid = y + ROW_H / 2
		p.append(
			f'<text x="{X_LAYER}" y="{mid + 5}" font-size="14.5" font-weight="700" fill="{INK}">{escape(layer)}</text>'
		)
		lines = wrap(tools, 40)[:3]
		for j, line in enumerate(lines):
			p.append(
				f'<text x="{X_TOOLS}" y="{mid + 5 - (len(lines) - 1) * 8 + j * 16}" font-size="12.5" fill="{MUTED}">{escape(line)}</text>'
			)
		colour = KINDS[kind]
		label = escape(kind)
		w = 26 + 7.7 * len(kind)
		p.append(f'<rect x="{X_KIND}" y="{mid - 13}" width="{w:.0f}" height="26" rx="13" fill="{colour}"/>')
		p.append(
			f'<text x="{X_KIND + 13}" y="{mid + 5}" font-size="13" font-weight="700" fill="#ffffff">{label}</text>'
		)
		lines = wrap(why, 56)[:3]
		for j, line in enumerate(lines):
			p.append(
				f'<text x="{X_WHY}" y="{mid + 5 - (len(lines) - 1) * 8 + j * 16}" font-size="12.5" fill="{INK}">{escape(line)}</text>'
			)
		p.append(f'<line x1="24" y1="{y + ROW_H}" x2="{W - 24}" y2="{y + ROW_H}" stroke="{LINE}"/>')
	legend_y = TOP + ROW_H * len(ROWS) + 32
	x = 32
	for name, colour, note in (
		("Replaces", GREEN, "does the job itself"),
		("Includes", BLUE, "built in"),
		("Complements", AMBER, "works beside it"),
		("Feeds", PLUM, "sends its records out"),
	):
		p.append(f'<rect x="{x}" y="{legend_y - 12}" width="14" height="14" rx="7" fill="{colour}"/>')
		p.append(
			f'<text x="{x + 22}" y="{legend_y}" font-size="13" fill="{INK}"><tspan font-weight="700">{name}</tspan> {note}</text>'
		)
		x += 270
	p.append("</svg>")
	OUT.write_text("\n".join(p), encoding="utf-8")
	print(OUT)


main()
