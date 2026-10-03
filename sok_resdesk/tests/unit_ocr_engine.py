"""The OCR engine (core/ocr_engine.py) on a rendered two-column Kannada page. Needs the tesseract
program with its Kannada model and a Kannada font (CI installs them); skipped without them."""

import glob
import io

import pytest

from sok_resdesk.core import ocr_engine, zones

PIL = pytest.importorskip("PIL")
FONTS = glob.glob("/usr/share/fonts/**/Lohit-Kannada.ttf", recursive=True) + glob.glob(
	"/usr/share/fonts/**/NotoSansKannada*.ttf", recursive=True
)
needs_tesseract = pytest.mark.skipif(
	"kan" not in ocr_engine.available() or not FONTS, reason="tesseract with Kannada, and a Kannada font"
)

LEFT = ["ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು", "ಮೊದಲನೆಯ ಭಾಗ", "ಹರಿದಾಸ ಸಾಹಿತ್ಯ"]
RIGHT = ["ಪುರಂದರ ದಾಸರು", "ಎರಡನೆಯ ಅಧ್ಯಾಯ", "ಕರ್ನಾಟಕ ಸಂಗೀತ"]


def two_column_page() -> bytes:
	from PIL import Image, ImageDraw, ImageFont

	img = Image.new("L", (1600, 900), 255)
	draw = ImageDraw.Draw(img)
	font = ImageFont.truetype(FONTS[0], 48)
	for i, (left, right) in enumerate(zip(LEFT, RIGHT, strict=True)):
		draw.text((60, 80 + i * 110), left, font=font, fill=0)
		draw.text((860, 80 + i * 110), right, font=font, fill=0)
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return buf.getvalue()


def words(text):
	return {w for w in text.split() if len(w) > 2}


def test_models_for_a_language():
	have = ["eng", "kan", "hin", "osd"]
	assert ocr_engine.models_for("kan", have) == "kan+eng"
	assert ocr_engine.models_for("kok", have) == "kan+eng"
	assert ocr_engine.models_for("hin, san", have) == "hin+eng"  # Sanskrit model not installed: Hindi's
	assert ocr_engine.models_for("", have) == "eng"
	with pytest.raises(ocr_engine.OcrError):
		ocr_engine.models_for("tam", ["osd"])


@needs_tesseract
def test_columns_are_read_apart_when_zoned():
	page = two_column_page()
	# the problem: read as one block, a line of the left column runs on into the right one
	whole = ocr_engine.read_page(page, None, "kan+eng")["text"].splitlines()[0]
	assert words(LEFT[0]) & words(whole) and words(RIGHT[0]) & words(whole), whole
	by_zone = ocr_engine.read_page(page, zones.presets()["Two columns"], "kan+eng")
	left_text, right_text = (p["text"] for p in by_zone["zones"])
	# each column's words come back in its own zone: the columns no longer mix
	assert words(" ".join(LEFT)) & words(left_text), left_text
	assert words(" ".join(RIGHT)) & words(right_text), right_text
	assert not (words(" ".join(RIGHT)) & words(left_text))
	assert not (words(" ".join(LEFT)) & words(right_text))
	assert by_zone["text"].index(left_text) < by_zone["text"].index(right_text)  # reading order
	# a skip zone is left out
	skip_right = [zones.zone(2, 2, 47, 96), zones.zone(50, 2, 48, 96, kind="skip")]
	only_left = ocr_engine.read_page(page, skip_right, "kan+eng")
	assert len(only_left["zones"]) == 1 and not (words(" ".join(RIGHT)) & words(only_left["text"]))


@needs_tesseract
def test_a_bad_image_is_an_ocr_error():
	with pytest.raises(ocr_engine.OcrError):
		ocr_engine.read_page(b"not an image", None, "kan+eng")
