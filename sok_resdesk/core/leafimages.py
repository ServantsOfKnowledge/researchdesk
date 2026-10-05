"""Books that are folders of photographs: a palm-leaf bundle, a manuscript, a bound volume shot page by page.

A folder of images (JPEG, PNG, TIFF) with no ``_meta.xml`` and no PDF is one book; its leaves are the
images in natural order of their names (``leaf2`` before ``leaf10``). A small ``bundle.json`` beside
the images may give its details. This module finds the leaves and reads, scales and converts them;
nothing here imports Frappe.
"""

from __future__ import annotations

import io
import json
import re

from sok_resdesk.core import media

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
SIDECAR = "bundle.json"
MAX_SIDE = 8000  # a longer side is scaled down when a leaf is first read (palm leaves are long and thin)
MAX_PIXELS = 120_000_000  # a larger photograph is refused (a decompression bomb, or a mistake)
MIN_LEAVES = 2


def natural_key(name: str) -> list:
	"""'leaf10.jpg' sorts after 'leaf2.jpg'."""
	return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def leaf_names(files: list[str]) -> list[str]:
	"""The images among `files`, in leaf order (hidden files and previews left out)."""
	images = [
		f
		for f in files
		if f.lower().endswith(IMAGE_EXT)
		and not f.startswith((".", "_"))
		and not f.lower().startswith("thumb")
	]
	return sorted(images, key=natural_key)


def is_bundle(files: list[str]) -> bool:
	"""A folder is a bundle of leaves when it has images, no IA metadata, no PDF and no Calibre book."""
	if any(f.endswith("_meta.xml") or f.lower().endswith(".pdf") for f in files):
		return False
	if any(media.is_media(f) for f in files):  # a recording's poster and stills are not leaves
		return False
	return len(leaf_names(files)) >= MIN_LEAVES or SIDECAR in files and bool(leaf_names(files))


def bundle_id(rel_path: str) -> str:
	"""`palm/Ramayana-bundle-3` → `img-palm-Ramayana-bundle-3`."""
	name = re.sub(r"[^\w.-]+", "-", rel_path.strip("/"), flags=re.UNICODE).strip("-")
	return f"img-{name}"[:140]


def sidecar_meta(raw: bytes | None, folder_name: str) -> dict:
	"""The bundle's details in IA's names, from `bundle.json` (title, creator, date, language,
	description, subject, publisher, item_type…) and the folder's name."""
	data: dict = {}
	if raw:
		try:
			loaded = json.loads(raw.decode("utf-8-sig"))
			data = loaded if isinstance(loaded, dict) else {}
		except ValueError:
			data = {}
	meta = {k: v for k, v in data.items() if k not in ("item_type", "ocr", "manuscript")}
	meta.setdefault("title", re.sub(r"[_]+", " ", folder_name).strip() or folder_name)
	meta.setdefault("mediatype", "image")
	return meta


def sidecar_options(raw: bytes | None) -> dict:
	"""What `bundle.json` says besides the details: the kind of work (a bundle is a Manuscript
	unless it says otherwise), whether to read it with OCR, and the manuscript's own fields."""
	try:
		data = json.loads(raw.decode("utf-8-sig")) if raw else {}
	except ValueError:
		data = {}
	data = data if isinstance(data, dict) else {}
	item_type = str(data.get("item_type") or "Manuscript")
	ms = data.get("manuscript") if isinstance(data.get("manuscript"), dict) else {}
	return {
		"item_type": item_type,
		"ocr": bool(data.get("ocr", item_type != "Manuscript")),
		"manuscript": {f"ms_{k}": v for k, v in ms.items() if isinstance(v, (str, int))},
	}


def open_image(source, max_side: int = MAX_SIDE):
	"""A Pillow image from a path or bytes, scaled so its longer side is at most `max_side`, upright
	(its EXIF orientation applied) and in RGB (or grey)."""
	from PIL import Image, ImageOps

	Image.MAX_IMAGE_PIXELS = MAX_PIXELS
	im = Image.open(source if isinstance(source, str) else io.BytesIO(source))
	im = ImageOps.exif_transpose(im)
	if im.mode not in ("RGB", "L"):
		im = im.convert("RGB")
	if max(im.size) > max_side:
		im.thumbnail((max_side, max_side))
	return im


def to_jpeg(im, quality: int = 88) -> bytes:
	buf = io.BytesIO()
	im.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
	return buf.getvalue()


def resize_to_width(data: bytes, width: int, quality: int = 85) -> bytes:
	"""A JPEG scaled to `width` px (never larger than it is)."""
	from PIL import Image

	with Image.open(io.BytesIO(data)) as im:
		if width <= 0 or width >= im.width:
			return data
		return to_jpeg(
			im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS), quality
		)
