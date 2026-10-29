"""Code 39 barcodes as SVG, for member cards and copy labels. Pure Python.

Code 39 is read by every handheld scanner, needs no check digit and has no library behind it: each
character is five bars and four spaces, three of the nine wide. A code is made of letters A-Z, digits and
- . space $ / + % (lower case is made upper case), between a start and stop `*`.
"""

from __future__ import annotations

# 1 = wide, 0 = narrow; bar, space, bar, space, ... (nine elements)
PATTERNS = {
	"0": "000110100", "1": "100100001", "2": "001100001", "3": "101100000", "4": "000110001",
	"5": "100110000", "6": "001110000", "7": "000100101", "8": "100100100", "9": "001100100",
	"A": "100001001", "B": "001001001", "C": "101001000", "D": "000011001", "E": "100011000",
	"F": "001011000", "G": "000001101", "H": "100001100", "I": "001001100", "J": "000011100",
	"K": "100000011", "L": "001000011", "M": "101000010", "N": "000010011", "O": "100010010",
	"P": "001010010", "Q": "000000111", "R": "100000110", "S": "001000110", "T": "000010110",
	"U": "110000001", "V": "011000001", "W": "111000000", "X": "010010001", "Y": "110010000",
	"Z": "011010000", "-": "010000101", ".": "110000100", " ": "011000100", "*": "010010100",
	"$": "010101000", "/": "010100010", "+": "010001010", "%": "000101010",
}  # fmt: skip

WIDE = 3  # a wide element is this many narrow ones


def clean(text: str) -> str:
	"""The text as Code 39 can carry it, or "" when it has a character it cannot."""
	text = (text or "").strip().upper()
	return text if text and all(c in PATTERNS and c != "*" for c in text) else ""


def bars(text: str) -> list[tuple[int, int]]:
	"""(x, width) of every bar, in narrow-element units, for the text between its start and stop."""
	out, x = [], 0
	for ch in f"*{text}*":
		for i, wide in enumerate(PATTERNS[ch]):
			w = WIDE if wide == "1" else 1
			if i % 2 == 0:
				out.append((x, w))
			x += w
		x += 1  # the narrow gap between characters
	return out


def svg(text: str, height: int = 48, module: int = 2, label: bool = True) -> str:
	"""An SVG of the barcode (with the text under it), or "" when the text cannot be a Code 39."""
	text = clean(text)
	if not text:
		return ""
	quiet = 10 * module  # blank space either side, so a scanner finds the start
	rects = bars(text)
	width = rects[-1][0] + rects[-1][1]
	total = width * module + 2 * quiet
	body = "".join(
		f'<rect x="{quiet + x * module}" y="0" width="{w * module}" height="{height}"/>' for x, w in rects
	)
	extra = 16 if label else 0
	caption = (
		f'<text x="{total / 2}" y="{height + 13}" text-anchor="middle" font-family="monospace" '
		f'font-size="13">{text}</text>'
		if label
		else ""
	)
	return (
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {height + extra}" '
		f'width="{total}" height="{height + extra}" role="img" aria-label="{text}">'
		f'<rect width="{total}" height="{height + extra}" fill="#fff"/><g fill="#000">{body}</g>{caption}</svg>'
	)
