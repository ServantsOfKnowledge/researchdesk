"""Burning boxes into page images. The result is a picture: nothing under a box (text layer, image data)
survives in it, which a black rectangle drawn over a PDF page does not give."""

from __future__ import annotations

import io

MAX_SIDE = 12_000  # pixels: a page image larger than this is refused rather than held in memory


class RedactError(ValueError):
	pass


def burn(png: bytes, boxes: list[dict], label: str = "") -> bytes:
	"""The page with each box (percent of the page) filled black; `label` is written small under each."""
	from PIL import Image, ImageDraw

	try:
		image = Image.open(io.BytesIO(png))
		if max(image.size) > MAX_SIDE:
			raise RedactError("The page image is too large.")
		image = image.convert("RGB")
	except (OSError, Image.DecompressionBombError) as e:
		raise RedactError("The page image can't be read.") from e
	w, h = image.size
	draw = ImageDraw.Draw(image)
	for b in boxes:
		x0, y0 = round(w * float(b["left"]) / 100), round(h * float(b["top"]) / 100)
		x1 = min(w, round(w * (float(b["left"]) + float(b["width"])) / 100))
		y1 = min(h, round(h * (float(b["top"]) + float(b["height"])) / 100))
		draw.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
		if label and y1 - y0 > 14:
			draw.text((x0 + 3, y0 + 2), label[:40], fill=(255, 255, 255))
	out = io.BytesIO()
	image.save(out, "PNG")
	return out.getvalue()


def pdf_of(paths: list[str], dpi: int) -> bytes:
	"""One PDF from page images kept on disk (each a picture only). The images are opened lazily and
	encoded one at a time, so a long book is not held in memory whole."""
	from PIL import Image

	if not paths:
		raise RedactError("No pages.")
	images = [Image.open(p) for p in paths]
	out = io.BytesIO()
	try:
		images[0].convert("RGB").save(
			out, "PDF", save_all=True, append_images=images[1:], resolution=float(dpi)
		)
	finally:
		for im in images:
			im.close()
	return out.getvalue()
