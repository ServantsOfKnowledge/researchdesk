"""Zones: the parts of a page image to OCR, in reading order. Pure Python.

Old books are set in columns, with headings across them, side notes, footnotes and pictures.
OCR of the whole page reads straight across the columns and mixes their lines; OCR of each part
on its own, joined in reading order, keeps them apart. A zone is a rectangle in percent of the
page image (so it fits any image size) with its place in the reading order and what it is:

* ``text``: read it (a column, a paragraph, a heading, a footnote);
* ``skip``: leave it out (a picture, a stamp, a running header the text shouldn't carry).

Zones are drawn by hand on a page, or come from a preset (whole page, two columns, three
columns, a heading over two columns) that can be applied to a page or to a whole book.
"""

from __future__ import annotations

import json
import re

KINDS = ("text", "skip")
MIN_SIZE = 1.0  # percent: anything smaller is a slip of the mouse


class ZoneError(ValueError):
	pass


def _clip(v: float) -> float:
	return round(min(100.0, max(0.0, float(v))), 2)


LANG = re.compile(r"^[a-z]{2,8}$")


def zone(x: float, y: float, w: float, h: float, kind: str = "text", langs=None) -> dict:
	"""One zone, kept inside the page. `langs`: the zone's own languages (codes), when they differ
	from the book's: a Sanskrit verse in a Kannada book."""
	if kind not in KINDS:
		raise ZoneError(f"a zone is text or skip, not {kind!r}")
	x, y = _clip(x), _clip(y)
	w, h = _clip(min(float(w), 100 - x)), _clip(min(float(h), 100 - y))
	if w < MIN_SIZE or h < MIN_SIZE:
		raise ZoneError("a zone must be at least 1% wide and high")
	out = {"x": x, "y": y, "w": w, "h": h, "kind": kind}
	codes = [str(c).strip().lower() for c in (langs or [])][:4]
	if any(not LANG.match(c) for c in codes):
		raise ZoneError("a zone's languages are codes such as kan, san, eng")
	if codes:
		out["langs"] = codes
	return out


def clean(zones) -> list[dict]:
	"""Zones from the reader (a list, or its JSON) checked and kept in the order given: that order
	is the reading order. At most 40 zones on a page."""
	if isinstance(zones, str):
		zones = json.loads(zones or "[]")
	out = []
	for z in (zones or [])[:40]:
		out.append(zone(z["x"], z["y"], z["w"], z["h"], z.get("kind") or "text", z.get("langs")))
	return out


def presets() -> dict[str, list[dict]]:
	"""Layouts to start from. Margins of 2% keep the page's edge (and its shadow) out."""
	m = 2.0
	full = 100 - 2 * m
	return {
		"Whole page": [zone(m, m, full, full)],
		"Two columns": [zone(m, m, full / 2, full), zone(50, m, full / 2, full)],
		"Three columns": [zone(m + i * full / 3, m, full / 3, full) for i in range(3)],
		"Heading and two columns": [
			zone(m, m, full, 12),
			zone(m, 14, full / 2, 100 - 14 - m),
			zone(50, 14, full / 2, 100 - 14 - m),
		],
	}


def in_reading_order(zones: list[dict]) -> list[dict]:
	"""Zones sorted the way a person reads them: full-width zones (headings) where they fall, and
	between them the columns left to right, each top to bottom. For a quick start ("Sort"); the
	order a person gives is the one used."""
	wide = sorted([z for z in zones if z["w"] >= 60], key=lambda z: z["y"])
	narrow = [z for z in zones if z["w"] < 60]
	column = lambda z: (round(z["x"] / 5), z["y"])  # noqa: E731 (zones a few percent apart line up)
	out: list[dict] = []
	for top, bottom in _bands(wide):
		out.extend(z for z in wide if z["y"] == top)
		out.extend(sorted((z for z in narrow if top <= z["y"] < bottom), key=column))
	return out


def _bands(wide: list[dict]) -> list[tuple[float, float]]:
	"""The stretches of the page between full-width zones: columns are read within each."""
	edges = sorted({0.0, *(z["y"] for z in wide)}) + [101.0]
	return list(zip(edges, edges[1:], strict=False))


def pixels(z: dict, width: int, height: int) -> tuple[int, int, int, int]:
	"""(left, top, right, bottom) in pixels of an image `width` × `height`."""
	left = int(round(z["x"] / 100 * width))
	top = int(round(z["y"] / 100 * height))
	right = int(round((z["x"] + z["w"]) / 100 * width))
	bottom = int(round((z["y"] + z["h"]) / 100 * height))
	left, top = min(max(0, left), width - 1), min(max(0, top), height - 1)  # at least one pixel
	return left, top, min(width, max(left + 1, right)), min(height, max(top + 1, bottom))


def join(texts: list[str]) -> str:
	"""The zones' texts as one page text: each zone a paragraph, in reading order."""
	return "\n\n".join(t.strip() for t in texts if t and t.strip())
