"""OCR of a page image, zone by zone, with Tesseract (and its Indic language models).

Each text zone (core/zones.py) is cut out of the page image and read on its own, so columns and
side notes don't run into each other; the zones' texts are joined in reading order. Tesseract
runs as a program (`tesseract`), installed in the Docker image with the language models the
libraries need (Kannada, Devanagari for Hindi, Marathi and Sanskrit, Tamil, Telugu, Malayalam,
Bengali, Gujarati, Gurmukhi, Oriya, and English).

Pure Python apart from Pillow (for cutting the image) and the tesseract program.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess

from sok_resdesk.core import zones as zn

# the book's language (ISO 639-3 as catalogued, or 639-1) → Tesseract models. English is added
# for the Latin words most Indic books carry (titles, names, numbers).
LANGS = {
	"kan": "kan",
	"kn": "kan",
	"kok": "kan",  # Konkani in Kannada script (as most of these books are)
	"tcy": "kan",  # Tulu
	"hin": "hin",
	"hi": "hin",
	"mar": "mar",
	"mr": "mar",
	"san": "san",
	"sa": "san",
	"nep": "nep",
	"tam": "tam",
	"ta": "tam",
	"tel": "tel",
	"te": "tel",
	"mal": "mal",
	"ml": "mal",
	"ben": "ben",
	"bn": "ben",
	"guj": "guj",
	"gu": "guj",
	"pan": "pan",
	"pa": "pan",
	"ori": "ori",
	"or": "ori",
	"urd": "urd",
	"ur": "urd",
	"eng": "eng",
	"en": "eng",
	"asm": "asm",
	"as": "asm",
}
# names, as catalogue labels write them ("Kannada; English")
NAMES = {
	"kannada": "kan", "konkani": "kan", "tulu": "kan", "hindi": "hin", "marathi": "mar",
	"sanskrit": "san", "nepali": "nep", "tamil": "tam", "telugu": "tel", "malayalam": "mal",
	"bengali": "ben", "bangla": "ben", "assamese": "asm", "gujarati": "guj", "punjabi": "pan",
	"oriya": "ori", "odia": "ori", "urdu": "urd", "english": "eng",
}  # fmt: skip
SPLIT = re.compile(r"[,;/|+]+|\s+and\s+")
TIMEOUT = 120  # seconds for one zone
PSM_BLOCK = "6"  # "a single uniform block of text": what a zone is


class OcrError(RuntimeError):
	pass


def available() -> list[str]:
	"""The language models Tesseract has here ([] when it isn't installed)."""
	if not shutil.which("tesseract"):
		return []
	try:
		out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=30)
	except (OSError, subprocess.TimeoutExpired):
		return []
	return [line.strip() for line in out.stdout.splitlines()[1:] if line.strip()]


def models_in(*languages) -> list[str]:
	"""The Tesseract models named by language codes, names or lists of them, in order:
	"kan", "Kannada; English", ["kan", "san"], "kan+san". Unknown ones are left out."""
	out = []
	for value in languages:
		for part in value if isinstance(value, list | tuple) else [value]:
			for token in SPLIT.split(str(part or "")):
				t = token.strip().lower()
				model = LANGS.get(t) or NAMES.get(t) or (t if t in LANGS.values() else None)
				if model and model not in out:
					out.append(model)
	return out


def models_for(language, have: list[str] | None = None) -> str:
	"""The Tesseract models for a book's language(s), e.g. "kan+san+eng", keeping only those
	installed. The first is the main one; English is always added for the Latin words most Indic
	books carry (titles, names, numbers)."""
	have = available() if have is None else have
	wanted = models_in(language) or ["eng"]
	if "eng" not in wanted:
		wanted.append("eng")
	usable = [m for m in dict.fromkeys(wanted) if m in have]
	if not usable:
		raise OcrError(
			f"No OCR model for {language or 'this language'} is installed (have: {', '.join(have) or 'none'})"
		)
	return "+".join(usable)


def _tesseract(png: bytes, models: str) -> str:
	try:
		out = subprocess.run(
			["tesseract", "stdin", "stdout", "-l", models, "--psm", PSM_BLOCK],
			input=png,
			capture_output=True,
			timeout=TIMEOUT,
		)
	except subprocess.TimeoutExpired as e:
		raise OcrError("OCR took too long on one zone") from e
	except OSError as e:
		raise OcrError(f"Tesseract could not run: {e}") from e
	if out.returncode != 0:
		raise OcrError((out.stderr or b"").decode("utf-8", "replace")[-300:] or "Tesseract failed")
	return out.stdout.decode("utf-8", "replace")


def read_page(image: bytes, zones: list[dict] | None, models: str) -> dict:
	"""OCR a page image. `zones` in reading order (None or [] for the whole page).
	Returns {text, zones: [{zone, text}]}."""
	from PIL import Image, ImageOps

	try:
		img = Image.open(io.BytesIO(image))
		img.load()
	except Exception as e:
		raise OcrError(f"The page image could not be read: {e}") from e
	img = ImageOps.exif_transpose(img).convert("L")  # greyscale: what Tesseract reads best
	zones = [z for z in (zones or []) if z.get("kind", "text") == "text"] or [zn.zone(0, 0, 100, 100)]
	have = None
	parts = []
	for z in zones:
		crop = img.crop(zn.pixels(z, img.width, img.height))
		if crop.width < 400:  # small zones read better a little bigger
			factor = 400 / crop.width
			crop = crop.resize((400, max(1, int(crop.height * factor))))
		buf = io.BytesIO()
		crop.save(buf, format="PNG")
		zone_models = models
		if z.get("langs"):  # a zone in its own language(s): a Sanskrit verse in a Kannada book
			have = available() if have is None else have
			zone_models = models_for(z["langs"], have)
		parts.append({"zone": z, "text": _tesseract(buf.getvalue(), zone_models).strip()})
	return {"text": zn.join([p["text"] for p in parts]), "zones": parts}
