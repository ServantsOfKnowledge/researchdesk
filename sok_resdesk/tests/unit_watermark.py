"""A name and date stamped across a page image."""

import io

import pytest

pytest.importorskip("PIL.Image")

from PIL import Image  # noqa: E402

from sok_resdesk.core import watermark  # noqa: E402


def _jpeg(colour=(255, 255, 255)):
	out = io.BytesIO()
	Image.new("RGB", (800, 1000), colour).save(out, "JPEG")
	return out.getvalue()


def test_the_page_keeps_its_size_and_gains_marks():
	stamped = watermark.stamp(_jpeg(), watermark.text_for("Test Reader", "2026-11-18"))
	image = Image.open(io.BytesIO(stamped))
	assert image.size == (800, 1000)
	assert image.convert("L").getextrema()[0] < 250  # grey marks on a white page


def test_an_unreadable_image_is_returned_as_it_was():
	assert watermark.stamp(b"not an image", "x") == b"not an image"
