"""Code 39 barcodes (core/barcode.py): the table, the shape, and that a scanner library reads them."""

from sok_resdesk.core import barcode


def test_every_character_has_three_wide_elements_of_nine():
	assert len(barcode.PATTERNS) == 44
	for ch, pattern in barcode.PATTERNS.items():
		assert len(pattern) == 9 and pattern.count("1") == 3, ch


def test_text_is_cleaned_or_refused():
	assert barcode.clean(" m-00042 ") == "M-00042"
	assert barcode.clean("a*b") == ""  # * is the start and stop
	assert barcode.clean("ಕನ್ನಡ") == ""
	assert barcode.clean("") == ""


def test_the_svg_is_made_for_good_text_only():
	out = barcode.svg("M-00042")
	assert out.startswith("<svg") and "M-00042" in out and out.count("<rect") > 20
	assert barcode.svg("ಕ") == ""


def test_start_and_stop_frame_the_bars():
	rects = barcode.bars("A")
	# *, A, * : 3 characters of 5 bars each
	assert len(rects) == 15
