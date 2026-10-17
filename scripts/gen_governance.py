#!/usr/bin/env python3
"""Draw the Governance Mode picture (sok_resdesk/public/images/governance.svg) for docs/governance.md.

    python3 scripts/gen_governance.py

Plain SVG with its own background, so it reads the same in light and dark themes.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "sok_resdesk" / "public" / "images" / "governance.svg"
W, H = 1200, 800
INK, MUTED, LINE, BG = "#1f272e", "#5b6670", "#9aa7b2", "#ffffff"
GREEN, BLUE, AMBER, PLUM, SLATE, RED = "#2f6f5e", "#2b5f9e", "#a8650c", "#7a3e8f", "#3d4852", "#a1362c"

parts: list[str] = [f'<rect width="{W}" height="{H}" fill="{BG}"/>']


def text(x, y, s, size=13, weight=400, fill=INK, anchor="start"):
	parts.append(
		f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>'
	)


def box(x, y, w, h, title, lines=(), colour=SLATE, fill="#f6f8fa", dash=False):
	d = ' stroke-dasharray="6 4"' if dash else ""
	parts.append(
		f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{colour}" stroke-width="1.6"{d}/>'
	)
	text(x + 12, y + 23, title, 14, 700, colour)
	for i, s in enumerate(lines):
		text(x + 12, y + 43 + i * 17, s, 12.5)


def arrow(x1, y1, x2, y2, colour=LINE, label=""):
	parts.append(
		f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{colour}" stroke-width="2" fill="none" marker-end="url(#a)"/>'
	)
	if label:
		text((x1 + x2) / 2 + 6, (y1 + y2) / 2 - 4, label, 12, 700, colour)


text(30, 32, "Governance Mode: who sees a classified record, and what is written down", 20, 700)

# --- panel 1: the decision, for every request ---------------------------------------------------
text(30, 66, "1  THE DECISION, ON EVERY REQUEST", 13, 700, MUTED)
box(30, 82, 150, 74, "A request", ("search, page, file,", "export, push"), BLUE, "#eef3fb")
box(
	220,
	82,
	200,
	74,
	"Plain rules",
	("guest mode, member,", "Public / Login to read / find"),
	SLATE,
)
box(
	460,
	82,
	190,
	74,
	"Cleared only?",
	("classified or scoped", "to a department"),
	AMBER,
	"#fbf3e8",
)
box(
	690,
	82,
	200,
	74,
	"Level high enough?",
	("clearance level ≥", "the record's level"),
	GREEN,
	"#eef3f1",
)
box(
	930,
	82,
	240,
	74,
	"In your offices?",
	("record's department is yours", "or below yours (or none)"),
	GREEN,
	"#eef3f1",
)
for a, b in ((180, 220), (420, 460), (650, 690), (890, 930)):
	arrow(a, 119, b, 119)
box(460, 196, 190, 80, "Shown as before", ("an ordinary record:", "only the plain rules", "apply"), SLATE)
arrow(555, 156, 555, 196, SLATE, "no")
box(
	690,
	196,
	250,
	64,
	"Not found: no trace",
	("not in search, counts, pages, files,", "exports, IIIF, OPDS, OAI-PMH, SRU, pushes"),
	RED,
	"#fbefed",
)
arrow(790, 156, 790, 196, RED, "no")
arrow(950, 156, 915, 196, RED, "no")
box(
	970,
	196,
	200,
	64,
	"Shown to you",
	("a signed-in person cleared;", "the Administrator sees all"),
	GREEN,
	"#eef3f1",
)
arrow(1070, 156, 1070, 196, GREEN, "yes")

# --- panel 2: the department tree ----------------------------------------------------------------
text(30, 304, "2  OFFICES READ DOWNWARD", 13, 700, MUTED)
tree = [
	(30, 316, "Secretariat department", "head office"),
	(80, 388, "Directorate", "sees the offices below"),
	(130, 460, "District office", "sees its taluks"),
	(180, 532, "Taluk office", "sees only its own"),
]
for x, y, t, s in tree:
	box(x, y, 250, 56, t, (s,), PLUM if x == 30 else SLATE, "#f6eef9" if x == 30 else "#f6f8fa")
for i in range(3):
	x, y = tree[i][0] + 70, tree[i][1] + 56
	arrow(x, y, x, y + 16, PLUM)
text(
	30,
	614,
	"A clearance is a level plus departments. An office never sees the records of the office above.",
	12.5,
	400,
	MUTED,
)

# --- panel 3: the audit chain -----------------------------------------------------------------------
text(480, 304, "3  THE AUDIT LOG IS A HASH CHAIN", 13, 700, MUTED)
for i in range(4):
	x = 480 + i * 175
	box(
		x,
		316,
		150,
		118,
		f"Line {i + 1}",
		("who · what · record", "when · address", f"hash(line {i}", " + this line)")
		if i
		else ("who · what · record", "when · address", "hash(start", " + this line)"),
		BLUE,
		"#eef3fb",
	)
	if i:
		arrow(x - 25, 375, x, 375, BLUE)
text(480, 456, "Change or remove a line anywhere and every hash after it stops matching:", 12.5)
text(480, 475, "“Check the log” says where. The hash is keyed with a secret kept outside the database.", 12.5)
box(
	480,
	496,
	330,
	94,
	"Written for",
	(
		"view · download · search",
		"change of visibility or classification",
		"clearances granted · sign-in · sign-out",
	),
	AMBER,
	"#fbf3e8",
)
box(
	840,
	496,
	330,
	94,
	"Cannot be",
	(
		"edited or deleted from the Desk or portal;",
		"a log cut short at its end shows only against",
		"the last line's number and hash, noted elsewhere",
	),
	RED,
	"#fbefed",
)

# --- panel 4: where it is enforced ------------------------------------------------------------------
text(30, 650, "4  WHERE IT IS ENFORCED", 13, 700, MUTED)
spots = [
	("Search", "engine filter on level and department"),
	("Lists and counts", "SQL condition on every portal count"),
	("Pages and files", "private, never cached"),
	("Feeds", "OAI-PMH · SRU · OPDS · IIIF: never"),
	("Exports and pushes", "never a classified record"),
	("The Desk", "lists and forms follow clearance"),
]
for i, (t, s) in enumerate(spots):
	x = 30 + i * 190
	parts.append(
		f'<rect x="{x}" y="664" width="180" height="84" rx="10" fill="#f6f8fa" stroke="{LINE}" stroke-width="1.4"/>'
	)
	text(x + 10, 688, t, 13, 700, SLATE)
	words = s.split(" ")
	line, y = "", 708
	for w in words:
		if len(line + w) > 24:
			text(x + 10, y, line.strip(), 12)
			line, y = "", y + 16
		line += w + " "
	text(x + 10, y, line.strip(), 12)
text(
	30,
	774,
	"Hidden classified records stay hidden even if Governance Mode is switched off: the switch only adds the people who are cleared.",
	12.5,
	400,
	MUTED,
)

svg = (
	f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
	'aria-labelledby="t d" font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">'
	'<title id="t">Governance Mode: who sees a classified record</title>'
	'<desc id="d">Every request passes the plain visibility rules, then a classified or department-scoped record is shown only '
	"to a signed-in person whose clearance level is high enough and whose offices include the record's department or are above it. "
	"Otherwise it is not found at all. Offices read downward. The audit log is a chain of hashed lines. Search, lists, pages, files, "
	"feeds, exports, pushes and the Desk all enforce it.</desc>"
	f'<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{LINE}"/></marker>'
	f'<marker id="r" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{RED}"/></marker></defs>'
	+ "".join(parts)
	+ "</svg>\n"
)
OUT.write_text(svg, encoding="utf-8")
print(OUT)
