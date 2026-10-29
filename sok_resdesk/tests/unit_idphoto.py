"""Photos sent from a browser (core/idphoto.py)."""

import base64
import io

import pytest

from sok_resdesk.core import idphoto

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def url(fmt="PNG", size=(40, 30), mime="png"):
	buf = io.BytesIO()
	Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
	return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def test_a_picture_is_drawn_again_as_a_small_jpeg():
	out = idphoto.clean(url(size=(3000, 2000)))
	img = Image.open(io.BytesIO(out))
	assert img.format == "JPEG" and max(img.size) <= idphoto.MAX_SIDE
	assert idphoto.mime_of(out) == "image/jpeg"


def test_only_jpeg_and_png_data_urls_pass():
	for bad in ("", "hello", "data:text/html;base64,PGI+", "data:image/gif;base64,R0lGODlhAQABAAAAACw="):
		with pytest.raises(idphoto.PhotoError):
			idphoto.clean(bad)


def test_a_file_that_is_not_the_picture_it_claims_is_refused():
	fake = "data:image/png;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
	with pytest.raises(idphoto.PhotoError):
		idphoto.clean(fake)
	gif = io.BytesIO()
	Image.new("RGB", (4, 4)).save(gif, "GIF")
	with pytest.raises(idphoto.PhotoError):  # a GIF under a PNG label
		idphoto.clean("data:image/png;base64," + base64.b64encode(gif.getvalue()).decode())


def test_a_large_file_is_refused():
	big = (
		"data:image/png;base64,"
		+ base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (idphoto.MAX_BYTES + 10)).decode()
	)
	with pytest.raises(idphoto.PhotoError):
		idphoto.clean(big)


def test_mime_is_sniffed_from_the_bytes():
	assert idphoto.mime_of(b"\x89PNG\r\n\x1a\nxxxx") == "image/png"
	assert idphoto.mime_of(b"GIF89a") == ""
