"""IIIF for the library's books (core/iiif.py has the formats).

    /iiif/<book>/manifest                      the book as a Presentation 3.0 manifest
    /iiif/<book>/text/<page>                   a page's text, as an annotation page
    /iiif/collection[/<collection>]            a collection of manifests (?page=2 for big ones)
    /iiif/image/<book>/<page>/info.json        the image service for pages drawn here from a PDF
    /iiif/image/<book>/<page>/full/800,/0/default.jpg

These are plain addresses under the portal, answered before Frappe routes the request
(`before_request` below), so IIIF viewers (Mirador, Universal Viewer…) can be pointed at them.
Who may see what is the same as on the portal: a book guests can't find is not found, one they
can find but not read asks for a login. Switched off with Settings → Features → Sharing metadata.
"""

from __future__ import annotations

import io
import json

import frappe
from frappe.utils import cint
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response

from sok_resdesk import access, features
from sok_resdesk.catalogue import base_url, get_record, portal_title
from sok_resdesk.core import iiif


class Served(HTTPException):
	"""Raised from before_request to answer with this response instead of routing the request."""

	def __init__(self, response: Response):
		super().__init__(response=response)
		self.code = response.status_code


def _json(data: dict, *, public: bool, status: int = 200, content_type: str = iiif.CONTENT_TYPE) -> Response:
	resp = Response(json.dumps(data, ensure_ascii=False), status=status, content_type=content_type)
	_headers(resp, public)
	return resp


def _headers(resp: Response, public: bool) -> None:
	if public:
		resp.headers["Access-Control-Allow-Origin"] = "*"  # viewers on other sites may use it
		resp.headers["Cache-Control"] = "public, max-age=300"
	else:
		resp.headers["Cache-Control"] = "private, no-store"  # members' books: this reader only


def _error(status: int, message: str) -> Response:
	resp = Response(
		json.dumps({"error": message}, ensure_ascii=False), status=status, content_type="application/json"
	)
	resp.headers["Cache-Control"] = "no-store"
	if status != 401:
		resp.headers["Access-Control-Allow-Origin"] = "*"
	return resp


# -- who may see a book ----------------------------------------------------------------------------


def _book(item_id: str) -> tuple[dict | None, Response | None]:
	"""The record, or the answer to give instead (404 not found, 401 login needed)."""
	record = get_record(item_id)
	if not record:
		return None, _error(404, "No such book")
	if not access.can_read(record.get("visibility")):
		return None, _error(401, "Log in to see this book")
	return record, None


def _public(record: dict) -> bool:
	return record.get("visibility") == "Public"


# -- the answers -----------------------------------------------------------------------------------


def _page_size(item_id: str) -> tuple[int, int]:
	"""The size of a page drawn from the book's PDF (its first, which the others follow)."""
	from PIL import Image

	from sok_resdesk.pdfs import page_jpeg

	with Image.open(io.BytesIO(page_jpeg(item_id, 0))) as im:
		return im.size


def drawn_here(record: dict) -> bool:
	"""Pages of this book are drawn here from its PDF (so this library serves the image)."""
	from sok_resdesk.pdfs import can_draw

	return not record.get("on_archive_org") and can_draw(record) and record.get("access_status") == "Open"


def manifest(item_id: str) -> Response:
	record, refused = _book(item_id)
	if refused:
		return refused
	base = base_url()
	if record.get("media"):
		return _media_manifest(record, base)
	local = drawn_here(record)
	size, pages = iiif.NOMINAL, cint(record.get("page_count"))
	if local:
		try:
			size = _page_size(item_id)
			if not pages:
				from sok_resdesk.core.pdfrender import page_count
				from sok_resdesk.pdfs import pdf_path

				pages = page_count(pdf_path(item_id))
		except Exception:
			local = False  # the PDF can't be read: no image service for it
	if record.get("on_archive_org") or record.get("from_wikisource"):
		from sok_resdesk.api import page_image_url  # archive.org's, or the Wikisource's, own images

		image_url = lambda leaf: page_image_url(record, leaf)  # noqa: E731
	elif local:
		image_url = lambda leaf: f"{iiif.service_id(base, item_id, leaf)}/full/max/0/default.jpg"  # noqa: E731
	else:
		return _error(404, "This book's page images are not available")
	if pages < 1:
		return _error(404, "This book's pages are not known yet")
	collections = frappe.get_all(
		"RD Collection",
		filters={
			"published": 1,
			"name": ("in", record.get("curated_collections") or ["-"]),
		},
		fields=["name", "title"],
		as_list=True,
	)
	data = iiif.manifest(
		record,
		base,
		provider=portal_title(),
		pages=pages,
		image_url=image_url,
		service=(lambda leaf: iiif.service(base, item_id, leaf)) if local else None,
		size=size,
		book_url=f"{base}/library/item/{item_id}",
		marcxml_url=f"{base}/api/method/sok_resdesk.api.marcxml?item_ids={item_id}",
		pdf_url=record.get("pdf_url") if record.get("access_status") == "Open" else "",
		text_pages=bool(record.get("has_page_text")),
		thumbnail=record.get("thumbnail_url") or "",
		collections=[(n, t) for n, t in collections],
	)
	return _json(data, public=_public(record))


def _media_manifest(record: dict, base: str) -> Response:
	from sok_resdesk.api import _segments

	item_id = record["item_id"]
	if record.get("access_status") != "Open":
		return _error(404, "This recording's files are not open")
	collections = frappe.get_all(
		"RD Collection",
		filters={"published": 1, "name": ("in", record.get("curated_collections") or ["-"])},
		fields=["name", "title"],
		as_list=True,
	)
	data = iiif.media_manifest(
		record,
		base,
		segments=_segments(record),
		provider=portal_title(),
		book_url=f"{base}/library/item/{item_id}",
		marcxml_url=f"{base}/api/method/sok_resdesk.api.marcxml?item_ids={item_id}",
		thumbnail=record.get("thumbnail_url") or "",
		collections=[(n, t) for n, t in collections],
	)
	return _json(data, public=_public(record))


def text(item_id: str, leaf: str) -> Response:
	record, refused = _book(item_id)
	if refused:
		return refused
	from sok_resdesk.ingest import fetch_pages

	try:
		pages = fetch_pages(item_id) if record.get("has_page_text") else []
	except Exception:
		pages = []
	here = next((p for p in pages if p["leaf"] == cint(leaf)), {})
	data = iiif.text_annotations(
		base_url(), item_id, cint(leaf), here.get("text") or "", record.get("language")
	)
	return _json(data, public=_public(record))


def collection(name: str, page: int = 1) -> Response:
	base = base_url()
	page = max(1, cint(page))
	if name:
		row = frappe.db.get_value(
			"RD Collection", {"name": name, "published": 1}, ["name", "title", "description"], as_dict=True
		)
		if not row:
			return _error(404, "No such collection")
		label, summary = row.title or name, frappe.utils.strip_html_tags(row.description or "")[:1000]
		parent = name
		subs = frappe.get_all(
			"RD Collection",
			filters={"published": 1, "part_of": name},
			fields=["name", "title"],
			as_list=True,
			order_by="sort_order asc, title asc",
		)
		ids = frappe.db.sql_list(
			"select parent from `tabRD Item Collection` where collection=%s and parenttype='RD Item'",
			name,
		)
	else:
		label, summary, parent, ids = portal_title(), "", "", []
		subs = frappe.get_all(
			"RD Collection",
			filters={"published": 1, "part_of": ("is", "not set")},
			fields=["name", "title"],
			as_list=True,
			order_by="sort_order asc, title asc",
		)
	items: list[tuple[str, str]] = []
	total = 0
	if parent:
		visible = [
			(i, t)
			for i, t, v in frappe.get_all(
				"RD Item",
				filters={"name": ("in", ids or ["-"]), "published": 1},
				fields=["name", "title", "visibility"],
				order_by="title asc",
				as_list=True,
			)
			if access.can_find(v)
		]
		total = len(visible)
		items = visible[(page - 1) * iiif.PER_PAGE : page * iiif.PER_PAGE]
	data = iiif.collection(
		base,
		label,
		items,
		name=parent,
		page=page,
		total=total,
		summary=summary,
		subcollections=[(n, t or n) for n, t in subs] if page == 1 else [],
	)
	return _json(data, public=True)


def _image_page(item_id: str, leaf: str) -> tuple[dict | None, int, Response | None]:
	record, refused = _book(item_id)
	if refused:
		return None, 0, refused
	if not drawn_here(record):
		return None, 0, _error(404, "This book's pages are served by archive.org (see the manifest)")
	return record, max(0, cint(leaf)), None


def image_info(item_id: str, leaf: str) -> Response:
	record, n, refused = _image_page(item_id, leaf)
	if refused:
		return refused
	try:
		width, height = _page_size_of(item_id, n)
	except Exception:
		return _error(404, "No such page")
	return _json(
		iiif.image_info(base_url(), item_id, n, width, height),
		public=_public(record),
		content_type=iiif.IMAGE_TYPE,
	)


def _page_size_of(item_id: str, leaf: int) -> tuple[int, int]:
	from PIL import Image

	from sok_resdesk.pdfs import page_jpeg

	with Image.open(io.BytesIO(page_jpeg(item_id, leaf))) as im:
		return im.size


def image(item_id: str, leaf: str, rest: str) -> Response:
	record, n, refused = _image_page(item_id, leaf)
	if refused:
		return refused
	from PIL import Image

	from sok_resdesk.core.pdfrender import RenderError
	from sok_resdesk.pdfs import page_jpeg

	try:
		with Image.open(io.BytesIO(page_jpeg(item_id, n))) as im:
			plan = iiif.image_plan(rest, *im.size)
			data, mimetype = iiif.render_plan(im.convert("RGB"), plan)
	except iiif.BadRequest as e:
		return _error(e.status, str(e))
	except (RenderError, OSError):
		return _error(404, "No such page")
	resp = Response(data, mimetype=mimetype)
	_headers(resp, _public(record))
	if _public(record):
		resp.headers["Cache-Control"] = "public, max-age=604800"
	return resp


# -- routing ---------------------------------------------------------------------------------------


def route(path: str, args) -> Response | None:
	"""The answer for a /iiif/… address, or None when it isn't one of ours."""
	parts = [p for p in path.split("/") if p]
	if not parts or parts[0] != "iiif":
		return None
	rest = parts[1:]
	if rest[:1] == ["collection"] and len(rest) <= 2:
		return collection(rest[1] if len(rest) == 2 else "", args.get("page") or 1)
	if rest[:1] == ["image"] and len(rest) >= 4:
		if rest[3:] == ["info.json"]:
			return image_info(rest[1], rest[2])
		return image(rest[1], rest[2], "/".join(rest[3:]))
	if len(rest) == 2 and rest[1] == "manifest":
		return manifest(rest[0])
	if len(rest) == 3 and rest[1] == "text":
		return text(rest[0], rest[2])
	return _error(404, "Not a IIIF address")


def before_request() -> None:
	"""hooks: answer /iiif/… here, so the addresses are plain (no /api/method/ in them)."""
	request = getattr(frappe, "request", None)
	if not request or not (request.path or "").startswith("/iiif/"):
		return
	if request.method == "OPTIONS":  # a viewer on another site asks first
		resp = Response(status=204)
		resp.headers["Access-Control-Allow-Origin"] = "*"
		resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
		raise Served(resp)
	if request.method not in ("GET", "HEAD"):
		raise Served(_error(405, "GET only"))
	if not features.on("sharing"):
		raise Served(_error(404, "IIIF is switched off for this library"))
	try:
		response = route(request.path, request.args)
	except frappe.DoesNotExistError:
		response = _error(404, "Not found")
	if response is not None:
		raise Served(response)
