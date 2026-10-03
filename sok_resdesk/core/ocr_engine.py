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
}
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


def models_for(language: str, have: list[str] | None = None) -> str:
	"""The Tesseract models for a book's language, e.g. "kan+eng", keeping only those installed."""
	have = available() if have is None else have
	codes = [c.strip().lower() for c in (language or "").replace(";", ",").split(",") if c.strip()]
	wanted = [LANGS[c] for c in codes if c in LANGS] or ["eng"]
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
	parts = []
	for z in zones:
		crop = img.crop(zn.pixels(z, img.width, img.height))
		if crop.width < 400:  # small zones read better a little bigger
			factor = 400 / crop.width
			crop = crop.resize((400, max(1, int(crop.height * factor))))
		buf = io.BytesIO()
		crop.save(buf, format="PNG")
		parts.append({"zone": z, "text": _tesseract(buf.getvalue(), models).strip()})
	return {"text": zn.join([p["text"] for p in parts]), "zones": parts}
