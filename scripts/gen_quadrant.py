#!/usr/bin/env python3
"""Draw a quadrant of digital library platforms (sok_resdesk/public/images/quadrant.svg).

    python3 scripts/gen_quadrant.py

A two-by-two in the familiar analyst layout. It is SOK's own, illustrative assessment, not an analyst
report: edit SCORES (0-100 on each axis) to change where a system sits, then run the script again.
X: breadth of what the system does across the layers of a digital library (repository, discovery, reader,
OCR and proofreading, preservation, archival description, deposit, sharing).
Y: fit for Indic-language collections and small institutions (self-hosted, light to run, Indic search and OCR).
"""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sok_resdesk" / "public" / "images" / "quadrant.svg"
INK, MUTED, LINE, BG = "#1f272e", "#5b6670", "#c9d2da", "#ffffff"
GREEN, GREY = "#2f6f5e", "#6b7782"
# name: (breadth, fit); first pass for the owner to review
SCORES = {
	"SOK Research Desk": (82, 88),
	"Greenstone": (60, 62),
	"Internet Archive": (75, 60),
	"Omeka": (45, 55),
	"DSpace": (55, 45),
	"EPrints": (50, 42),
	"CONTENTdm": (58, 30),
}
W, H = 1200, 860
L, T, S = 130, 120, 640  # plot area: left, top, side
LABEL_OFFSET = {
	"SOK Research Desk": (-20, 5),
	"EPrints": (12, 22),
	"DSpace": (12, -10),
	"Omeka": (-12, 22),
	"Greenstone": (12, -10),
}


def px(v: float) -> float:
	return L + S * v / 100


def py(v: float) -> float:
	return T + S * (1 - v / 100)


def main() -> None:
	p = [
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
		'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
		'aria-label="Quadrant of digital library platforms by breadth of capability and fit for Indic-language '
		'collections and small institutions">',
		f'<rect width="{W}" height="{H}" fill="{BG}"/>',
		f'<text x="32" y="46" font-size="24" font-weight="700" fill="{INK}">Digital library platforms: where each one sits</text>',
		f'<text x="32" y="72" font-size="14" fill="{MUTED}">SOK\'s own illustrative assessment, not an independent analyst report</text>',
	]
	# the four boxes
	half = S / 2
	for name, x, y, tint in (
		("NICHE PLAYERS", L, T + half, "#f6f8fa"),
		("VISIONARIES", L + half, T + half, "#eef5f2"),
		("CHALLENGERS", L, T, "#f6f8fa"),
		("LEADERS", L + half, T, "#eef5f2"),
	):
		p.append(f'<rect x="{x}" y="{y}" width="{half}" height="{half}" fill="{tint}" stroke="{LINE}"/>')
	for name, x, y in (
		("CHALLENGERS", L + 14, T + 26),
		("LEADERS", L + S - 14, T + 26),
		("NICHE PLAYERS", L + 14, T + S - 14),
		("VISIONARIES", L + S - 14, T + S - 14),
	):
		anchor = "end" if x > L + half else "start"
		p.append(
			f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="13" font-weight="700" letter-spacing="1.4" fill="{MUTED}">{name}</text>'
		)
	# axes
	p.append(
		f'<text x="{L + S / 2}" y="{T + S + 46}" text-anchor="middle" font-size="14" font-weight="700" fill="{INK}">BREADTH OF WHAT IT DOES  →</text>'
	)
	p.append(
		f'<text x="{L + S / 2}" y="{T + S + 66}" text-anchor="middle" font-size="12" fill="{MUTED}">repository, discovery, reader, OCR and proofreading, preservation, archival description, deposit, sharing</text>'
	)
	p.append(
		f'<text transform="translate(52 {T + S / 2}) rotate(-90)" text-anchor="middle" font-size="14" font-weight="700" fill="{INK}">FIT FOR INDIC COLLECTIONS AND SMALL INSTITUTIONS  →</text>'
	)
	p.append(
		f'<text transform="translate(72 {T + S / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="{MUTED}">self-hosted, light to run, Indic search and OCR</text>'
	)
	# the systems
	for name, (x, y) in SCORES.items():
		us = name.startswith("SOK")
		colour = GREEN if us else GREY
		dx, dy = LABEL_OFFSET.get(name, (14, 5))
		anchor = "end" if dx < 0 else "start"
		p.append(
			f'<circle cx="{px(x):.0f}" cy="{py(y):.0f}" r="{13 if us else 9}" fill="{colour}" stroke="#ffffff" stroke-width="2"/>'
		)
		p.append(
			f'<text x="{px(x) + dx + (-4 if us else 0):.0f}" y="{py(y) + dy:.0f}" text-anchor="{anchor}" '
			f'font-size="{15 if us else 13.5}" font-weight="{700 if us else 500}" fill="{INK}">{escape(name)}</text>'
		)
	p.append(
		f'<text x="{L + S + 40}" y="{T + 30}" font-size="13" font-weight="700" fill="{INK}">How to read it</text>'
	)
	notes = [
		"Right: does more of the digital",
		"library job in one system.",
		"Up: easier to run for a small",
		"library, and works well with",
		"Indian languages.",
		"",
		"Placements are a first pass",
		"for review: change SCORES in",
		"scripts/gen_quadrant.py.",
		"Systems are digital library",
		"platforms; library systems",
		"(Koha) and viewers (Mirador)",
		"are not plotted.",
	]
	for i, line in enumerate(notes):
		p.append(
			f'<text x="{L + S + 40}" y="{T + 54 + i * 19}" font-size="12.5" fill="{MUTED}">{escape(line)}</text>'
		)
	p.append("</svg>")
	OUT.write_text("\n".join(p), encoding="utf-8")
	print(OUT)


main()
