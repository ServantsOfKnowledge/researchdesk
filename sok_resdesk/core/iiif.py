"""IIIF for the library's books: Presentation API 3.0 manifests and a small Image API 3.0
service. No Frappe imports: the glue (iiif.py) gathers what these functions need.

* A **manifest** per book (`/iiif/<book>/manifest`): its metadata, one canvas per page with the
  page image painted on it, the PDF as a rendering, MARCXML and archive.org's own manifest as
  "see also", and the page text of each page as a supplementing annotation. Any IIIF viewer
  (Mirador, Universal Viewer, Annona…) opens it.
* A **collection** per Research Desk collection (`/iiif/collection/<name>`) and one for the whole
  library (`/iiif/collection`), listing manifests.
* An **image service** (level 0) for books whose pages are drawn here from their PDF
  (`/iiif/image/<book>/<page>/…`): fixed widths, `max`, `full`, no cropping or rotation.
  Books on archive.org have their pages served by archive.org, and the manifest points there.
"""

from __future__ import annotations

import re

PRESENTATION = "http://iiif.io/api/presentation/3/context.json"
IMAGE = "http://iiif.io/api/image/3/context.json"
CONTENT_TYPE = f'application/ld+json;profile="{PRESENTATION}"'
IMAGE_TYPE = f'application/ld+json;profile="{IMAGE}"'
IMAGE_WIDTHS = (400, 800, 1600)  # what the image service serves, besides "max"
NOMINAL = (1000, 1400)  # a page's size on its canvas when it isn't known (viewers use the image)
PER_PAGE = 200  # manifests in one page of a collection
# rights must be one of these (IIIF Presentation 3.0 §3.3)
RIGHTS_HOSTS = ("creativecommons.org", "rightsstatements.org")
IA_MANIFEST = "https://iiif.archive.org/iiif/{id}/manifest.json"

_LANG = re.compile(r"^[a-z]{2,3}$")


def lang(code: str | None) -> str:
	"""A language code a language map may use, else "none"."""
	code = (code or "").strip().lower()
	return code if _LANG.match(code) else "none"


def value(text: str, code: str | None = None) -> dict:
	return {lang(code): [text]}


def pair(label: str, text, code: str | None = None) -> dict | None:
	"""A metadata entry; None when there is nothing to show."""
	if isinstance(text, (list, tuple)):
		text = [t for t in text if t]
		if not text:
			return None
		return {"label": {"en": [label]}, "value": {lang(code): [str(t) for t in text]}}
	if not text:
		return None
	return {"label": {"en": [label]}, "value": {lang(code): [str(text)]}}


# -- ids -------------------------------------------------------------------------------------------


def book_id(base: str, item_id: str) -> str:
	return f"{base}/iiif/{item_id}/manifest"


def canvas_id(base: str, item_id: str, leaf: int) -> str:
	return f"{base}/iiif/{item_id}/canvas/{leaf}"


def text_id(base: str, item_id: str, leaf: int) -> str:
	return f"{base}/iiif/{item_id}/text/{leaf}"


def service_id(base: str, item_id: str, leaf: int) -> str:
	return f"{base}/iiif/image/{item_id}/{leaf}"


def collection_id(base: str, name: str = "", page: int = 1) -> str:
	url = f"{base}/iiif/collection" + (f"/{name}" if name else "")
	return url if page <= 1 else f"{url}?page={page}"


# -- the manifest ----------------------------------------------------------------------------------


def manifest(
	record: dict,
	base: str,
	*,
	provider: str,
	pages: int,
	image_url,
	service=None,
	size=NOMINAL,
	book_url: str = "",
	marcxml_url: str = "",
	pdf_url: str = "",
	text_pages: bool = False,
	thumbnail: str = "",
	collections: list[tuple[str, str]] | None = None,
) -> dict:
	"""The book as a Presentation 3.0 manifest.

	image_url(leaf) is the page image's address; service(leaf), when given, the image service
	that serves it ({"id", "type", "profile"}); size the canvas size (width, height)."""
	item_id = record["item_id"]
	code = record.get("language")
	width, height = size
	creators = [c for c in record.get("creators") or [] if c]
	meta = [
		pair("Author", creators, code),
		pair("Date", record.get("year") or record.get("date_raw")),
		pair("Publisher", record.get("publisher"), code),
		pair("Place", record.get("place"), code),
		pair("Language", record.get("language_label") or record.get("language")),
		pair("Subject", record.get("subjects") or [], code),
		pair("Series", record.get("series"), code),
		pair("ISBN", record.get("isbn")),
		pair("Identifier", record.get("ark") or record.get("persistent_id")),
		pair("DOI", record.get("doi")),
		pair("Source", record.get("source_url")),
		*[pair(m["label"], m["value"]) for m in record.get("manuscript") or []],
	]
	out: dict = {
		"@context": PRESENTATION,
		"id": book_id(base, item_id),
		"type": "Manifest",
		"label": value(record.get("title") or item_id, code),
		"metadata": [m for m in meta if m],
		"requiredStatement": {
			"label": {"en": ["Attribution"]},
			"value": value(
				record.get("rights") or f"Digitised books of {provider}",
				None if record.get("rights") else "en",
			),
		},
		"provider": [
			{
				"id": base,
				"type": "Agent",
				"label": value(provider, "en"),
				"homepage": [
					{"id": base, "type": "Text", "label": value(provider, "en"), "format": "text/html"}
				],
			}
		],
		"items": [],
	}
	if record.get("description"):
		out["summary"] = value(record["description"][:1000], code)
	licence = record.get("licence_url") or ""
	if any(f"//{h}/" in licence or licence.startswith(f"https://{h}") for h in RIGHTS_HOSTS):
		out["rights"] = licence
	if thumbnail:
		out["thumbnail"] = [{"id": thumbnail, "type": "Image", "format": "image/jpeg"}]
	if book_url:
		out["homepage"] = [
			{
				"id": book_url,
				"type": "Text",
				"label": value("The book's page in the library", "en"),
				"format": "text/html",
			}
		]
	if pdf_url:
		out["rendering"] = [
			{"id": pdf_url, "type": "Text", "label": value("PDF", "en"), "format": "application/pdf"}
		]
	see = []
	if marcxml_url:
		see.append(
			{
				"id": marcxml_url,
				"type": "Dataset",
				"label": value("MARCXML", "en"),
				"format": "application/marcxml+xml",
			}
		)
	if record.get("on_archive_org"):
		see.append(
			{
				"id": IA_MANIFEST.format(id=item_id),
				"type": "Manifest",
				"label": value("archive.org's own IIIF manifest", "en"),
				"format": "application/ld+json",
			}
		)
	if see:
		out["seeAlso"] = see
	if collections:
		out["partOf"] = [
			{"id": collection_id(base, name), "type": "Collection", "label": value(label)}
			for name, label in collections
		]
	for leaf in range(max(0, pages)):
		cid = canvas_id(base, item_id, leaf)
		body: dict = {
			"id": image_url(leaf),
			"type": "Image",
			"format": "image/jpeg",
			"width": width,
			"height": height,
		}
		svc = service(leaf) if service else None
		if svc:
			body["service"] = [svc]
		canvas = {
			"id": cid,
			"type": "Canvas",
			"label": {"none": [(record.get("leaf_labels") or {}).get(leaf) or str(leaf + 1)]},
			"width": width,
			"height": height,
			"items": [
				{
					"id": f"{cid}/page",
					"type": "AnnotationPage",
					"items": [
						{
							"id": f"{cid}/image",
							"type": "Annotation",
							"motivation": "painting",
							"body": body,
							"target": cid,
						}
					],
				}
			],
		}
		if text_pages:
			canvas["annotations"] = [{"id": text_id(base, item_id, leaf), "type": "AnnotationPage"}]
		out["items"].append(canvas)
	return out


def media_manifest(record: dict, base: str, segments: list[dict] | None = None, **kw) -> dict:
	"""A recording as a Manifest: one Canvas with a duration, painted with its sound or video, and
	the transcript as supplementing annotations that point at time ranges (`canvas#t=start,end`)."""
	rec = record["media"]
	files = rec["files"]
	kind = "Sound" if rec["kind"] == "Audio" else "Video"
	segs = [s for s in segments or [] if (s.get("text") or "").strip()]
	duration = rec.get("duration") or max([s["end"] for s in segments or []] + [0])
	out = manifest(record, base, pages=0, image_url=lambda _leaf: "", **kw)
	cid = canvas_id(base, record["item_id"], 0)
	body = {"id": files[0]["url"], "type": kind, "format": files[0]["mime"], "duration": duration}
	if len(files) > 1:  # the other formats: a choice, the first the default
		body = {
			"type": "Choice",
			"items": [
				{"id": f["url"], "type": kind, "format": f["mime"], "duration": duration} for f in files
			],
		}
	canvas: dict = {
		"id": cid,
		"type": "Canvas",
		"label": value(record.get("title") or record["item_id"], record.get("language")),
		"duration": duration,
		"items": [
			{
				"id": f"{cid}/page",
				"type": "AnnotationPage",
				"items": [
					{
						"id": f"{cid}/media",
						"type": "Annotation",
						"motivation": "painting",
						"body": body,
						"target": cid,
					}
				],
			}
		],
	}
	if kind == "Video":
		canvas["width"], canvas["height"] = 1280, 720
	if segs:
		code = lang(record.get("language"))
		canvas["annotations"] = [
			{
				"id": f"{cid}/transcript",
				"type": "AnnotationPage",
				"items": [
					{
						"id": f"{cid}/transcript/{n}",
						"type": "Annotation",
						"motivation": "supplementing",
						"body": {
							"type": "TextualBody",
							"value": s["text"],
							"format": "text/plain",
							**({"language": code} if code != "none" else {}),
						},
						"target": f"{cid}#t={s['start']:g},{s['end']:g}",
					}
					for n, s in enumerate(segs)
				],
			}
		]
	out["items"] = [canvas]
	return out


def text_annotations(base: str, item_id: str, leaf: int, text: str, code: str | None = None) -> dict:
	"""The text of one page as an annotation page that supplements its canvas."""
	body = {"type": "TextualBody", "value": text, "format": "text/plain"}
	if lang(code) != "none":
		body["language"] = lang(code)
	items = []
	if text.strip():
		items.append(
			{
				"id": f"{text_id(base, item_id, leaf)}/1",
				"type": "Annotation",
				"motivation": "supplementing",
				"body": body,
				"target": canvas_id(base, item_id, leaf),
			}
		)
	return {
		"@context": PRESENTATION,
		"id": text_id(base, item_id, leaf),
		"type": "AnnotationPage",
		"items": items,
	}


# -- collections -----------------------------------------------------------------------------------


def collection(
	base: str,
	label: str,
	items: list[tuple[str, str]],
	*,
	name: str = "",
	page: int = 1,
	total: int | None = None,
	summary: str = "",
	subcollections: list[tuple[str, str]] | None = None,
) -> dict:
	"""A Collection of manifests (and sub-collections): `items` are (item_id, title) of this page.
	A big collection comes in pages of PER_PAGE (?page=2…), each linking the next."""
	total = len(items) if total is None else total
	out: dict = {
		"@context": PRESENTATION,
		"id": collection_id(base, name, page),
		"type": "Collection",
		"label": value(label),
		"items": [
			{"id": collection_id(base, n), "type": "Collection", "label": value(t)}
			for n, t in (subcollections or [])
		]
		+ [{"id": book_id(base, i), "type": "Manifest", "label": value(t)} for i, t in items],
	}
	if summary:
		out["summary"] = value(summary[:1000])
	if page > 1:
		out["partOf"] = [{"id": collection_id(base, name), "type": "Collection", "label": value(label)}]
	if page * PER_PAGE < total:
		out["next"] = {"id": collection_id(base, name, page + 1), "type": "Collection"}
	return out


# -- the image service -----------------------------------------------------------------------------


def sizes_for(width: int, height: int) -> list[dict]:
	"""The widths listed for a page `width` × `height` px (never larger than the page), smallest first."""
	widths = sorted({w for w in IMAGE_WIDTHS if w < width} | {width})
	return [{"width": w, "height": max(1, round(height * w / width))} for w in widths]


TILE = 512
PROFILE = "level2"
MAX_OUT_PIXELS = 25_000_000  # the biggest image one request may ask for


def image_info(base: str, item_id: str, leaf: int, width: int, height: int) -> dict:
	scale, factors = 1, []
	while True:  # tiles at every scale, down to the first at which the whole page fits one tile
		factors.append(scale)
		if max(width, height) // scale < TILE:
			break
		scale *= 2
	return {
		"@context": IMAGE,
		"id": service_id(base, item_id, leaf),
		"type": "ImageService3",
		"protocol": "http://iiif.io/api/image",
		"profile": PROFILE,
		"width": width,
		"height": height,
		"maxWidth": width,
		"sizes": sizes_for(width, height),
		"tiles": [{"width": TILE, "height": TILE, "scaleFactors": factors}],
		"extraFormats": ["png"],
		"extraQualities": ["color", "gray", "bitonal"],
		"extraFeatures": ["mirroring", "sizeUpscaling"],
	}


def service(base: str, item_id: str, leaf: int) -> dict:
	return {"id": service_id(base, item_id, leaf), "type": "ImageService3", "profile": PROFILE}


class BadRequest(ValueError):
	"""An image request that can't be served (status 400, or 501 for a feature not offered)."""

	def __init__(self, message: str, status: int = 400):
		super().__init__(message)
		self.status = status


_NUM = r"\d+(?:\.\d+)?"


def _region(region: str, width: int, height: int) -> tuple[int, int, int, int]:
	if region in ("full", "max"):
		return 0, 0, width, height
	if region == "square":
		side = min(width, height)
		return (width - side) // 2, (height - side) // 2, (width + side) // 2, (height + side) // 2
	pct = region.startswith("pct:")
	body = region[4:] if pct else region
	m = re.fullmatch(rf"({_NUM}),({_NUM}),({_NUM}),({_NUM})", body)
	if not m:
		raise BadRequest("A region is full, square, x,y,w,h or pct:x,y,w,h")
	x, y, w, h = (float(v) for v in m.groups())
	if pct:
		x, y, w, h = x * width / 100, y * height / 100, w * width / 100, h * height / 100
	left, top = round(x), round(y)
	right, bottom = min(width, round(x + w)), min(height, round(y + h))
	if left >= width or top >= height or right <= left or bottom <= top:
		raise BadRequest("That region is outside the page or has no area")
	return left, top, right, bottom


def _size(size: str, rw: int, rh: int) -> tuple[int, int]:
	up = size.startswith("^")
	body = size[1:] if up else size
	if body in ("max", "full"):
		w, h = rw, rh
	elif m := re.fullmatch(rf"pct:({_NUM})", body):
		f = float(m.group(1)) / 100
		w, h = round(rw * f), round(rh * f)
	elif m := re.fullmatch(r"!(\d+),(\d+)", body):
		f = min(int(m.group(1)) / rw, int(m.group(2)) / rh)
		w, h = round(rw * f), round(rh * f)
	elif m := re.fullmatch(r"(\d+),(\d+)", body):
		w, h = int(m.group(1)), int(m.group(2))
	elif m := re.fullmatch(r"(\d+),", body):
		w = int(m.group(1))
		h = round(rh * w / rw)
	elif m := re.fullmatch(r",(\d+)", body):
		h = int(m.group(1))
		w = round(rw * h / rh)
	else:
		raise BadRequest("A size is max, w, ,h, w,h, !w,h or pct:n")
	if w < 1 or h < 1:
		raise BadRequest("That size has no pixels")
	if (w > rw or h > rh) and not up:
		raise BadRequest("The page is not served larger than it is (^ asks for that)")
	if w * h > MAX_OUT_PIXELS:
		raise BadRequest("That image is larger than this server makes")
	return w, h


def image_plan(rest: str, width: int, height: int) -> dict:
	"""`{region}/{size}/{rotation}/{quality}.{format}` for a page `width` × `height` → what to make:
	{"region": (left, top, right, bottom), "size": (w, h), "rotation": 0/90/180/270, "mirror": bool,
	"quality": "color"/"gray"/"bitonal", "format": "jpg"/"png"} (IIIF Image API 3.0, level 2)."""
	parts = rest.strip("/").split("/")
	if len(parts) != 4:
		raise BadRequest("An image request is region/size/rotation/quality.format")
	region, size, rotation, last = parts
	quality, _, fmt = last.partition(".")
	box = _region(region, width, height)
	out = _size(size, box[2] - box[0], box[3] - box[1])
	mirror = rotation.startswith("!")
	if (rotation[1:] if mirror else rotation) not in ("0", "90", "180", "270"):
		raise BadRequest("Pages turn in quarters only (0, 90, 180, 270)", 501)
	if quality not in ("default", "color", "gray", "bitonal"):
		raise BadRequest("Qualities are default, color, gray and bitonal", 501)
	if fmt not in ("jpg", "png"):
		raise BadRequest("Pages are served as .jpg or .png", 501)
	return {
		"region": box,
		"size": out,
		"rotation": int(rotation.lstrip("!")),
		"mirror": mirror,
		"quality": "color" if quality == "default" else quality,
		"format": fmt,
	}


def render_plan(im, plan: dict) -> tuple[bytes, str]:
	"""The image the plan asks for, cut from the Pillow image `im`: (bytes, content type)."""
	import io

	from PIL import Image, ImageOps

	out = im.crop(plan["region"])
	if out.size != plan["size"]:
		out = out.resize(plan["size"], Image.LANCZOS)
	if plan["mirror"]:
		out = ImageOps.mirror(out)
	if plan["rotation"]:
		out = out.rotate(-plan["rotation"], expand=True)  # clockwise, as IIIF turns
	if plan["quality"] == "gray":
		out = out.convert("L")
	elif plan["quality"] == "bitonal":
		out = out.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
	buf = io.BytesIO()
	if plan["format"] == "png":
		out.save(buf, "PNG")
		return buf.getvalue(), "image/png"
	out.convert("RGB").save(buf, "JPEG", quality=85)
	return buf.getvalue(), "image/jpeg"
