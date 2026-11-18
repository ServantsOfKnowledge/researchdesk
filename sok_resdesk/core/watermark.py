"""A faint name and date across a page image, so a copy of it can be traced to the reader (pure Pillow)."""

from __future__ import annotations

import io


def stamp(jpeg: bytes, text: str) -> bytes:
	"""`jpeg` with `text` repeated diagonally across it in light grey, as a new JPEG. The original is
	returned unchanged when the image cannot be read (a stamp must never stop a page showing)."""
	try:
		from PIL import Image, ImageDraw, ImageFont

		base = Image.open(io.BytesIO(jpeg)).convert("RGBA")
		size = max(14, base.width // 40)
		font = ImageFont.load_default(size)
		layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
		draw = ImageDraw.Draw(layer)
		step = int(size * 7)
		for y in range(-base.height, base.height * 2, step):
			for x in range(-base.width, base.width * 2, int(draw.textlength(text, font=font)) + size * 3):
				draw.text((x, y), text, font=font, fill=(110, 110, 110, 70))
		tilted = layer.rotate(25, resample=Image.BICUBIC)
		out = io.BytesIO()
		Image.alpha_composite(base, tilted).convert("RGB").save(out, "JPEG", quality=85)
		return out.getvalue()
	except Exception:
		return jpeg


def text_for(name: str, date: str) -> str:
	return f"{(name or '').strip()[:60]} · {date}"
