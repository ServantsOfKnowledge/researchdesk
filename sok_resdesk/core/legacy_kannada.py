"""Old Kannada font text: which fonts there are and whether a page of text is in one. Pure Python.

Before Unicode, Kannada was typed in fonts (Nudi, Baraha, ShreeLipi…) that put Kannada letters on the
Latin keys and accented Latin characters. A PDF made with such a font keeps those characters as its
text, so the book reads as `PÀ£ÀßqÀ` instead of `ಕನ್ನಡ` and cannot be searched. The conversion itself is the
Sanchaya converter's (sok_resdesk/vendor/kannada_font_converter); this module only says what to
convert.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

OFF = "Off"
FONTS = {  # setting label -> converter code
	"Nudi / Baraha": "nudi",
	"ShreeLipi (KAN-850)": "shree",
	"Prakashak (Praja)": "prakashak",
	"Akruti (Mono)": "akruti",
	"Surabhi (KND-series)": "surabhi",
	"ISM (KNTT-Nandi)": "ismkntt",
	"Dharma ILs": "dharma",
	"Janna Mono": "janna",
	"SriLipi 850": "srilipi850",
	"Shree Deccan": "shreedeccan",
	"Surabhi KN": "surabhikn",
	"Suchi Kan": "suchikan",
	"ISM (KNB TT-Nandi)": "ismknbtt",
	"Akruti Bi": "akrutibi",
	"WinKey KanEng": "winkey",
}
OPTIONS = "\n".join([OFF, *FONTS])

KANNADA = re.compile("[ಀ-೿]")
LATIN1 = re.compile(
	"[\u00a1-\u00ff]"
)  # inverted exclamation mark to y-diaeresis: where the fonts put the Kannada signs and most letters
MIN_CHARS = 30  # less than this is not enough to tell
LEGACY_SHARE = 0.25  # such characters among all characters: French is about 0.05, Nudi about 0.5
KANNADA_SHARE = 0.05


def code_for(label: str | None) -> str | None:
	"""The converter's code for a setting value; None for Off or anything unknown."""
	return FONTS.get(label or "")


def looks_legacy(text: str) -> bool:
	"""Whether `text` is full of accented Latin characters and has next to no Kannada: text in an old font."""
	chars = [c for c in text if not c.isspace()]
	if len(chars) < MIN_CHARS:
		return False
	kannada = len(KANNADA.findall(text))
	legacy = len(LATIN1.findall(text))
	return kannada / len(chars) < KANNADA_SHARE and legacy / len(chars) >= LEGACY_SHARE


# -- the engine, run as a separate program ----------------------------------------------------------

SCRIPT = os.path.join(
	os.path.dirname(os.path.dirname(__file__)), "vendor", "kannada_font_converter", "convert.js"
)
TIMEOUT = 120  # seconds for one batch
# The engine takes about 0.2 ms a character on the worst text (many one-letter words): a batch of this
# size is well inside the timeout, and a book is converted in several of them.
MAX_CHARS = 300_000


class ConverterError(Exception):
	pass


def convert(texts: list[str], font: str = "nudi", direction: str = "a2u", digits: str = "keep") -> list[str]:
	"""Each text converted by the Sanchaya engine (vendor/kannada_font_converter, GPL-3.0-or-later), run as
	`node convert.js` with JSON in and out. Raises ConverterError if Node is missing or the engine fails."""
	node = shutil.which("node")
	if not node:
		raise ConverterError("Node.js is not installed on this server")
	if sum(len(t) for t in texts) > MAX_CHARS:
		raise ConverterError("too much text for one conversion")
	payload = json.dumps(
		{"items": texts, "font": font, "direction": direction, "digits": digits, "retainEnglish": True}
	)
	try:
		env = {k: v for k, v in os.environ.items() if k != "NODE_OPTIONS"}  # nothing it should not obey
		done = subprocess.run(
			[node, SCRIPT],
			input=payload,
			capture_output=True,
			text=True,
			timeout=TIMEOUT,
			check=False,
			env=env,
		)
	except subprocess.TimeoutExpired as e:
		raise ConverterError("the converter took too long") from e
	if done.returncode:
		raise ConverterError((done.stderr or "the converter failed")[:300])
	items = json.loads(done.stdout).get("items")
	if not isinstance(items, list) or len(items) != len(texts):
		raise ConverterError("the converter returned the wrong number of texts")
	return items
