"""A photo of an ID card (or a member's photo) sent from a browser as a data URL, made safe to keep.

Only JPEG and PNG, at most MAX_BYTES, decoded and drawn again as a JPEG no larger than MAX_SIDE: whatever
else was in the file (metadata, a second format hidden in it, an oversized canvas) is gone. Needs Pillow.
"""

from __future__ import annotations

import base64
import binascii
import io
import re

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 1000
MAX_PIXELS = 30_000_000  # refuse a "decompression bomb" before drawing it

_DATA = re.compile(r"^data:image/(?:jpeg|png);base64,([A-Za-z0-9+/=\s]+)$")


class PhotoError(ValueError):
	pass


def clean(data_url: str) -> bytes:
	"""JPEG bytes of the picture, or PhotoError (its text is for the person)."""
	match = _DATA.match(data_url or "")
	if not match:
		raise PhotoError("Send a JPEG or PNG picture.")
	try:
		raw = base64.b64decode(re.sub(r"\s", "", match.group(1)), validate=True)
	except (binascii.Error, ValueError):
		raise PhotoError("That picture could not be read.") from None
	if len(raw) > MAX_BYTES:
		raise PhotoError("That picture is too large (2 MB at most).")
	from PIL import Image, UnidentifiedImageError

	try:
		probe = Image.open(io.BytesIO(raw))
		if probe.format not in ("JPEG", "PNG") or probe.width * probe.height > MAX_PIXELS:
			raise PhotoError("Send a JPEG or PNG picture.")
		probe.verify()
		image = Image.open(io.BytesIO(raw))
		image.thumbnail((MAX_SIDE, MAX_SIDE))
		out = io.BytesIO()
		image.convert("RGB").save(out, "JPEG", quality=85)
	except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
		raise PhotoError("That picture could not be read.") from None
	return out.getvalue()


def mime_of(content: bytes) -> str:
	"""image/jpeg or image/png from the first bytes ("" for anything else)."""
	if content[:3] == b"\xff\xd8\xff":
		return "image/jpeg"
	if content[:8] == b"\x89PNG\r\n\x1a\n":
		return "image/png"
	return ""
