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
	"""The widths served for a page `width` × `height` px (never larger than the page), smallest first."""
	widths = sorted({w for w in IMAGE_WIDTHS if w < width} | {width})
	return [{"width": w, "height": max(1, round(height * w / width))} for w in widths]


def image_info(base: str, item_id: str, leaf: int, width: int, height: int) -> dict:
	sizes = sizes_for(width, height)
	return {
		"@context": IMAGE,
		"id": service_id(base, item_id, leaf),
		"type": "ImageService3",
		"protocol": "http://iiif.io/api/image",
		"profile": "level0",
		"width": width,
		"height": height,
		"maxWidth": width,
		"sizes": sizes,
	}


def service(base: str, item_id: str, leaf: int) -> dict:
	return {"id": service_id(base, item_id, leaf), "type": "ImageService3", "profile": "level0"}


class BadRequest(ValueError):
	"""An image request the level 0 service doesn't serve (status 400, or 501 for a feature)."""

	def __init__(self, message: str, status: int = 400):
		super().__init__(message)
		self.status = status


def parse_image_request(rest: str, page_width: int) -> int:
	"""`{region}/{size}/{rotation}/{quality}.{format}` → the width to serve.

	Level 0: the whole page only (region `full`), at `max` or one of the listed widths (`w,`),
	unrotated (`0`), `default` quality, as JPEG."""
	parts = rest.strip("/").split("/")
	if len(parts) != 4:
		raise BadRequest("An image request is region/size/rotation/quality.format")
	region, size, rotation, last = parts
	quality, _, fmt = last.partition(".")
	if region not in ("full", "max"):
		raise BadRequest("Only the whole page is served (region full)", 501)
	if rotation != "0":
		raise BadRequest("Pages are not rotated (rotation 0)", 501)
	if quality != "default":
		raise BadRequest("Only the default quality is served", 501)
	if fmt != "jpg":
		raise BadRequest("Pages are served as JPEG (.jpg)", 501)
	if size in ("max", "full"):
		return page_width
	m = re.fullmatch(r"\^?(\d+),", size)
	if not m:
		raise BadRequest("Sizes are max or a width such as 800,", 501)
	want = int(m.group(1))
	if want not in {s["width"] for s in sizes_for(page_width, 1)}:
		raise BadRequest(
			f"Served widths: {', '.join(str(s['width']) for s in sizes_for(page_width, 1))}", 501
		)
	return want
