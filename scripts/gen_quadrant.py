#!/usr/bin/env python3
"""Draw a quadrant of the systems Research Desk is compared with (sok_resdesk/public/images/quadrant.svg).

    python3 scripts/gen_quadrant.py

A two-by-two in the familiar analyst layout. It is SOK's own, illustrative assessment, not an analyst
report: edit SCORES (0-100 on each axis) to change where a system sits, then run the script again.
Every system named in "Where it fits" of docs/architecture.md is here, coloured by the layer it is for.
X: breadth of what the system does across the layers of a digital library (repository, discovery, reader,
OCR and proofreading, preservation, archival description, deposit, sharing). A tool for one layer is
narrow by design, so it sits to the left.
Y: fit for Indic-language collections and small institutions (self-hosted, light to run, Indic search and OCR).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sok_resdesk" / "public" / "images" / "quadrant.svg"
INK, MUTED, LINE, BG = "#1f272e", "#5b6670", "#c9d2da", "#ffffff"
US = "#2f6f5e"
# layer -> colour
LAYERS = {
	"Repository / digital library": "#2b5f9e",
	"Discovery and reader": "#0e8a8a",
	"OCR and proofreading": "#a8650c",
	"Preservation": "#7a3e8f",
	"Library system": "#b0413e",
	"Aggregator": "#6b7782",
	"Digitisation workflow": "#8a7a1f",
	"Archival description": "#4a6b2a",
}
# name: (breadth, fit, layer); a first pass for the owner to review
SCORES = {
	"SOK Research Desk": (82, 88, None),
	"Greenstone": (60, 62, "Repository / digital library"),
	"Omeka": (45, 55, "Repository / digital library"),
	"DSpace": (55, 45, "Repository / digital library"),
	"EPrints": (50, 42, "Repository / digital library"),
	"CONTENTdm": (58, 30, "Repository / digital library"),
	"Internet Archive": (75, 60, "Aggregator"),
	"VuFind": (22, 50, "Discovery and reader"),
	"Blacklight": (20, 38, "Discovery and reader"),
	"IA BookReader": (11, 56, "Discovery and reader"),
	"Mirador": (10, 48, "Discovery and reader"),
	"Universal Viewer": (14, 42, "Discovery and reader"),
	"Tesseract scripts": (15, 68, "OCR and proofreading"),
	"FromThePage": (24, 46, "OCR and proofreading"),
	"Archivematica": (32, 34, "Preservation"),
	"Preservica": (36, 22, "Preservation"),
	"LOCKSS": (20, 33, "Preservation"),
	"Koha": (40, 72, "Library system"),
	"Evergreen": (34, 40, "Library system"),
	"SOUL": (28, 58, "Library system"),
	"e-Granthalaya": (26, 64, "Library system"),
	"NDLI": (44, 66, "Aggregator"),
	"Europeana": (38, 28, "Aggregator"),
	"DPLA": (30, 26, "Aggregator"),
	"Wikidata": (18, 60, "Aggregator"),
	"Wikimedia Commons": (22, 54, "Aggregator"),
	"Wikisource": (27, 52, "Aggregator"),
	"Goobi": (39, 36, "Digitisation workflow"),
	"Kitodo": (36, 30, "Digitisation workflow"),
	"Scribe": (16, 30, "Digitisation workflow"),
	"AtoM": (35, 50, "Archival description"),
	"ArchivesSpace": (41, 44, "Archival description"),
}
W, H = 1500, 1000
L, T, S = 130, 110, 780  # plot area: left, top, side
FONT = 12.5


def px(v: float) -> float:
	return L + S * v / 100


def py(v: float) -> float:
	return T + S * (1 - v / 100)


def place_labels() -> dict[str, tuple[float, float, str]]:
	"""A spot for each label that overlaps no dot and no other label: name -> (x, y, text-anchor)."""
	boxes: list[tuple[float, float, float, float]] = []
	for _name, (x, y, _layer) in SCORES.items():
		boxes.append((px(x) - 10, py(y) - 10, px(x) + 10, py(y) + 10))
	out = {}
	for name, (x, y, _layer) in sorted(SCORES.items(), key=lambda kv: -kv[1][0]):
		w, h = 6.5 * len(name), 14
		cx, cy = px(x), py(y)
		options = [
			(cx + 13, cy + 4, "start"), (cx - 13, cy + 4, "end"), (cx + 13, cy - 11, "start"),
			(cx - 13, cy - 11, "end"), (cx + 13, cy + 19, "start"), (cx - 13, cy + 19, "end"),
			(cx, cy - 15, "middle"), (cx, cy + 24, "middle"),
		]  # fmt: skip
		for tx, ty, anchor in options:
			x0 = tx if anchor == "start" else tx - w if anchor == "end" else tx - w / 2
			box = (x0, ty - h + 3, x0 + w, ty + 3)
			if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in boxes):
				break
		boxes.append(box)
		out[name] = (tx, ty, anchor)
	return out


def main() -> None:
	p = [
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
		'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
		'aria-label="Quadrant of the systems Research Desk is compared with, by breadth of what they do and '
		'fit for Indic-language collections and small institutions">',
		f'<rect width="{W}" height="{H}" fill="{BG}"/>',
		f'<text x="32" y="46" font-size="24" font-weight="700" fill="{INK}">Where each system sits</text>',
		f'<text x="32" y="72" font-size="14" fill="{MUTED}">SOK\'s own illustrative assessment of the systems '
		"Research Desk is compared with, not an independent analyst report</text>",
	]
	half = S / 2
	for x, y, tint in (
		(L, T + half, "#f6f8fa"), (L + half, T + half, "#eef5f2"), (L, T, "#f6f8fa"), (L + half, T, "#eef5f2")
	):  # fmt: skip
		p.append(f'<rect x="{x}" y="{y}" width="{half}" height="{half}" fill="{tint}" stroke="{LINE}"/>')
	for name, x, y in (
		("CHALLENGERS", L + 14, T + 26), ("LEADERS", L + S - 14, T + 26),
		("NICHE PLAYERS", L + 14, T + S - 14), ("VISIONARIES", L + S - 14, T + S - 14),
	):  # fmt: skip
		anchor = "end" if x > L + half else "start"
		p.append(
			f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="13" font-weight="700" '
			f'letter-spacing="1.4" fill="{MUTED}">{name}</text>'
		)
	p.append(
		f'<text x="{L + S / 2}" y="{T + S + 44}" text-anchor="middle" font-size="14" font-weight="700" '
		f'fill="{INK}">BREADTH OF WHAT IT DOES  →</text>'
	)
	p.append(
		f'<text x="{L + S / 2}" y="{T + S + 64}" text-anchor="middle" font-size="12" fill="{MUTED}">'
		"repository, discovery, reader, OCR and proofreading, preservation, archival description, deposit, "
		"sharing. A tool for one layer is narrow by design.</text>"
	)
	p.append(
		f'<text transform="translate(52 {T + S / 2}) rotate(-90)" text-anchor="middle" font-size="14" '
		f'font-weight="700" fill="{INK}">FIT FOR INDIC COLLECTIONS AND SMALL INSTITUTIONS  →</text>'
	)
	p.append(
		f'<text transform="translate(72 {T + S / 2}) rotate(-90)" text-anchor="middle" font-size="12" '
		f'fill="{MUTED}">self-hosted, light to run, Indic search and OCR</text>'
	)
	spots = place_labels()
	for name, (x, y, layer) in SCORES.items():
		us = layer is None
		colour = US if us else LAYERS[layer]
		tx, ty, anchor = spots[name]
		p.append(
			f'<circle cx="{px(x):.0f}" cy="{py(y):.0f}" r="{13 if us else 8}" fill="{colour}" '
			'stroke="#ffffff" stroke-width="2"/>'
		)
		p.append(
			f'<text x="{tx:.0f}" y="{ty:.0f}" text-anchor="{anchor}" font-size="{15 if us else FONT}" '
			f'font-weight="{700 if us else 500}" fill="{INK}">{escape(name)}</text>'
		)
	lx = L + S + 36
	p.append(
		f'<text x="{lx}" y="{T + 14}" font-size="13" font-weight="700" fill="{INK}">What each dot is for</text>'
	)
	rows = [("SOK Research Desk", US), *LAYERS.items()]
	for i, (label, colour) in enumerate(rows):
		y = T + 44 + i * 26
		p.append(f'<circle cx="{lx + 7}" cy="{y - 4}" r="7" fill="{colour}"/>')
		p.append(f'<text x="{lx + 22}" y="{y}" font-size="13" fill="{INK}">{escape(label)}</text>')
	notes = [
		"Right: does more of the digital",
		"library job in one system.",
		"Up: easier to run for a small",
		"library, and works well with",
		"Indian languages.",
		"",
		"Placements are a first pass for",
		"review: change SCORES in",
		"scripts/gen_quadrant.py.",
	]
	for i, line in enumerate(notes):
		p.append(
			f'<text x="{lx}" y="{T + 300 + i * 19}" font-size="12.5" fill="{MUTED}">{escape(line)}</text>'
		)
	p.append("</svg>")
	OUT.write_text("\n".join(p), encoding="utf-8")
	print(OUT)


main()
