"""A PDF's pages as images: for OCR, for proofreading and for *Page & text*.

Poppler's ``pdftoppm`` renders any page (text, vector drawings, every image compression); it is
in the Docker image and in the native installs' packages. Without it, the page's largest
embedded image is taken with pypdf, which is what a scan's page is, in most PDFs.

Pure Python (subprocess, pypdf, Pillow) so it is unit-tested directly.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile

OCR_DPI = 300  # what Tesseract reads best
VIEW_DPI = 110  # a page on screen
TIMEOUT = 120


class RenderError(RuntimeError):
	pass


def poppler() -> bool:
	return bool(shutil.which("pdftoppm"))


def page_count(path: str) -> int:
	from pypdf import PdfReader

	return len(PdfReader(path).pages)


def render(path: str, leaf: int, dpi: int = OCR_DPI, grey: bool = True, fmt: str = "png") -> bytes:
	"""Page `leaf` (from 0) of the PDF at `path`, as PNG (for OCR) or JPEG (for the screen)."""
	if poppler():
		return _pdftoppm(path, leaf, dpi, grey, fmt)
	return _largest_image(path, leaf, dpi, grey, fmt)


def _pdftoppm(path: str, leaf: int, dpi: int, grey: bool, fmt: str) -> bytes:
	with tempfile.TemporaryDirectory() as tmp:
		out = os.path.join(tmp, "page")
		args = ["pdftoppm", "-f", str(leaf + 1), "-l", str(leaf + 1), "-r", str(dpi), "-singlefile"]
		args += ["-gray"] if grey else []
		args += ["-jpeg", "-jpegopt", "quality=82"] if fmt == "jpeg" else ["-png"]
		try:
			done = subprocess.run([*args, path, out], capture_output=True, timeout=TIMEOUT)
		except subprocess.TimeoutExpired as e:
			raise RenderError(f"page {leaf + 1} took too long to draw") from e
		name = out + (".jpg" if fmt == "jpeg" else ".png")
		if done.returncode != 0 or not os.path.exists(name):
			raise RenderError((done.stderr or b"").decode("utf-8", "replace")[-300:] or "pdftoppm failed")
		with open(name, "rb") as f:
			return f.read()


def _largest_image(path: str, leaf: int, dpi: int, grey: bool, fmt: str) -> bytes:
	"""The page's biggest embedded image (a scanned page), scaled to about `dpi`."""
	from PIL import Image
	from pypdf import PdfReader

	reader = PdfReader(path)
	if leaf >= len(reader.pages):
		raise RenderError(f"the PDF has {len(reader.pages)} pages")
	page = reader.pages[leaf]
	best = None
	try:
		for img in page.images:
			pic = img.image
			if pic is not None and (best is None or pic.width * pic.height > best.width * best.height):
				best = pic
	except Exception as e:  # an image compression pypdf can't read (JBIG2 without its decoder)
		raise RenderError(f"page {leaf + 1}: {e}") from e
	if best is None:
		raise RenderError(f"page {leaf + 1} has no image (install poppler-utils to draw it)")
	width_in = float(page.mediabox.width) / 72 or 8.5
	scale = min(1.0, dpi * width_in / best.width)
	if scale < 1.0:
		best = best.resize((max(1, int(best.width * scale)), max(1, int(best.height * scale))), Image.LANCZOS)
	best = best.convert("L" if grey else "RGB")
	buf = io.BytesIO()
	best.save(buf, format="JPEG" if fmt == "jpeg" else "PNG", **({"quality": 82} if fmt == "jpeg" else {}))
	return buf.getvalue()


def pdf_info(path: str) -> dict:
	"""What a PDF says about itself: {title, author, subject, keywords}. Not its dates: they
	say when the file was made (the scan), not when the book was published."""
	from pypdf import PdfReader

	try:
		info = PdfReader(path).metadata or {}
	except Exception:
		return {}

	def clean(key):
		value = info.get(key)
		return str(value).strip() if value else ""

	return {
		"title": clean("/Title"),
		"author": clean("/Author"),
		"subject": clean("/Subject"),
		"keywords": clean("/Keywords"),
	}
