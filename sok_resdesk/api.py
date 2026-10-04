"""Public API for the Research Desk portal and third-party tools.

All endpoints live under /api/method/sok_resdesk.api.<name> and are readable by
guests (published records only). What a guest sees also depends on each book's
visibility and the site's guest access setting (see access.py); logged-in readers
see everything published. See docs/api.md for examples.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint
from werkzeug.wrappers import Response

from sok_resdesk import access
from sok_resdesk.catalogue import base_url, get_record
from sok_resdesk.core import citations, marc
from sok_resdesk.search import PAGES_MAX_HITS, MeiliClient, SearchError, _quote
from sok_resdesk.search import search as _search

MAX_BATCH = 500


def _loads(value, default):
	if value in (None, ""):
		return default
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except ValueError:
		frappe.throw(_("Invalid JSON parameter"))


def _text_response(body: str, content_type: str, filename: str | None = None) -> Response:
	resp = Response(body, content_type=f"{content_type}; charset=utf-8")
	if filename:
		resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
	resp.headers["Access-Control-Allow-Origin"] = "*"
	return resp


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def search(q: str = "", mode: str = "books", filters=None, page: int = 1, per_page: int = 20, sort: str = ""):
	"""Search books (metadata + excerpt) or pages (full text inside books).

	filters: JSON object, e.g. {"language_label": ["Kannada"], "decade": ["1950s"], "year_from": 1900}
	"""
	try:
		result = _search(
			q,
			"pages" if mode == "pages" else "books",
			_loads(filters, {}),
			page,
			per_page,
			sort,
			access={"books": access.search_filter("books"), "pages": access.search_filter("pages")},
		)
	except SearchError as e:
		frappe.log_error("Research Desk: search failed", str(e))
		frappe.throw(_("Search is temporarily unavailable."), title=_("Search"))
	return {
		"query": q,
		"mode": mode,
		"page": result.get("page", 1),
		"total_pages": result.get("totalPages", 0),
		"total": result.get("totalHits", result.get("estimatedTotalHits", 0)),
		# the engine counts matching pages only up to a limit: the portal shows "10,000+"
		"total_capped": mode == "pages" and result.get("totalHits", 0) >= PAGES_MAX_HITS,
		"took_ms": result.get("processingTimeMs"),
		"facets": result.get("facetDistribution", {}),
		"hits": [_hit(h, mode) for h in result.get("hits", [])],
		# true when this visitor must log in to search this way (e.g. inside the text)
		"login_needed": bool(result.get("restricted")),
		# Indic spellings searched too, for a query typed in Latin letters: [{script, q}]
		"also": result.get("also") or [],
	}


def _hit(hit: dict, mode: str) -> dict:
	f = hit.get("_formatted", {})
	out = {
		"item_id": hit["item_id"],
		"title": hit.get("title"),
		"alt_title": hit.get("alt_title"),
		"title_html": f.get("title") or frappe.utils.escape_html(hit.get("title") or ""),
		"creators": hit.get("creators") or [],
		"year": hit.get("year"),
		"language": hit.get("language_label"),
		"visibility": hit.get("visibility") or access.PUBLIC,
		"url": f"/library/item/{hit['item_id']}",
	}
	if mode == "pages":
		leaf = hit.get("leaf", 0)
		out.update(
			{
				"leaf": leaf,
				"page_label": hit.get("label") or "",
				"snippet": f.get("text", ""),
				"url": f"/library/item/{hit['item_id']}?page={leaf}",
			}
		)
	else:
		out.update(
			{
				"thumbnail": hit.get("thumbnail_url"),
				"page_count": hit.get("page_count"),
				"subjects": (hit.get("subjects") or [])[:5],
				"access": hit.get("access_status"),
				"has_fulltext": hit.get("has_fulltext"),
				"snippet": f.get("text_excerpt")
				if "<mark>" in (f.get("text_excerpt") or "")
				else f.get("description", ""),
			}
		)
	return out


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def search_inside(item_id: str, q: str, limit: int = 50):
	"""Pages of one book that match `q`, with highlighted snippets."""
	if not q.strip():
		return {"hits": []}
	row = frappe.db.get_value("RD Item", item_id, ["published", "visibility"], as_dict=True)
	if not row or not row.published or not access.can_find(row.visibility):
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	if not access.can_read(row.visibility):
		return {"total": 0, "hits": [], "login_needed": True}
	from sok_resdesk.search import expand_query, federated

	client = MeiliClient.from_settings()
	limit = min(cint(limit) or 50, 200)
	body = {
		"q": q,
		"filter": f"item_id = {_quote(item_id)}",
		"limit": limit,
		"sort": ["leaf:asc"],
		"attributesToCrop": ["text"],
		"cropLength": 30,
		"attributesToHighlight": ["text"],
		"highlightPreTag": "<mark>",
		"highlightPostTag": "</mark>",
		"attributesToRetrieve": ["leaf", "label"],
	}
	# a word typed in Latin letters also finds its spelling in the book's own script
	language = frappe.db.get_value("RD Item", item_id, "language_label")
	queries, also = expand_query(q, {"language_label": [language]} if language else None, client)
	if len(queries) > 1:
		result = federated(
			client, client.pages, queries, {k: v for k, v in body.items() if k != "sort"}, 1, limit
		)
		result["hits"].sort(key=lambda h: h.get("leaf", 0))
		result["estimatedTotalHits"] = result["totalHits"]
	else:
		result = client.search(client.pages, body)
	return {
		"also": also,
		"total": result.get("estimatedTotalHits", 0),
		"hits": [
			{
				"leaf": h["leaf"],
				"page_label": h.get("label"),
				"snippet": h.get("_formatted", {}).get("text", ""),
			}
			for h in result.get("hits", [])
		],
	}


# -- the page reader (book page → "Page & text") ---------------------------------------------------


def page_image_url(record: dict, leaf: int) -> str:
	"""The page image: archive.org serves every page of a book it holds as …/page/n<leaf>.jpg.
	Books only in the library's own folders have no page images here yet (their PDF has them)."""
	if record.get("on_archive_org"):
		from urllib.parse import quote

		return f"https://archive.org/download/{quote(record['item_id'], safe='')}/page/n{int(leaf)}.jpg"
	return ""


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=240, seconds=60)
def page(item_id: str, leaf: int = 0):
	"""One page for the page reader: its image, its text and printed number, and its neighbours.
	`leaf` counts the page images from 0 (as archive.org does)."""
	from sok_resdesk.ingest import fetch_pages

	record = get_record(item_id)
	if not record:
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	if not access.can_read(record.get("visibility")):
		return {"login_needed": True}
	try:
		pages = fetch_pages(item_id) if record.get("has_page_text") else []
	except Exception:
		pages = []  # the image can still be shown
	by_leaf = {p["leaf"]: p for p in pages}
	last = max([cint(record.get("page_count")) - 1, *(by_leaf or [0])])
	leaf = min(max(0, cint(leaf)), max(0, last))
	here = by_leaf.get(leaf) or {}
	from sok_resdesk import pagetext

	version = pagetext.current(item_id).get(leaf)
	return {
		# where the text comes from: archive.org's OCR, a re-OCR, or people (with their names: credit)
		"text_status": version.status if version else "",
		"text_source": version.source if version else "",
		"proofread_by": frappe.utils.get_fullname(version.proofread_by)
		if version and version.proofread_by
		else "",
		"validated_by": frappe.utils.get_fullname(version.validated_by)
		if version and version.validated_by
		else "",
		"can_proofread": pagetext.can_proofread(),
		"leaf": leaf,
		"last": last,
		"label": here.get("label") or "",
		"text": here.get("text") or "",
		"has_text": bool(pages),
		"image": page_image_url(record, leaf),
		"pdf": record.get("pdf_url") if record.get("access_status") == "Open" else "",
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def cite_page(item_id: str, leaf: int = 0, label: str = ""):
	"""Citations of one page in every format, linking to that page."""
	record = get_record(item_id)
	if not record:
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	cited = citations.with_page(record, cint(leaf), (label or "")[:20], base_url())
	return {
		"url": cited["page_url"],
		"page": citations.page_phrase(cited),
		"formats": {k: citations.render(cited, k, base_url()) for k in citations.FORMATS},
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def item(item_id: str):
	record = get_record(item_id)
	if not record:
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	record.pop("modified", None)
	record.pop("set_specs", None)
	record["can_read"] = access.can_read(record.get("visibility"))
	if not record["can_read"]:
		record["pdf_url"] = ""
	record["portal_url"] = f"{base_url()}/library/item/{item_id}"
	record["citation_formats"] = {k: v[0] for k, v in citations.FORMATS.items()}
	return record


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=300, seconds=60)
def cite(item_id: str, format: str = "bibtex", download: int = 0):
	"""One record as BibTeX, BibLaTeX, RIS, CSL-JSON, APA, MLA or Chicago."""
	record = get_record(item_id)
	if not record:
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	fmt = format.lower()
	if fmt not in citations.FORMATS:
		frappe.throw(_("Unknown format. Use one of: {0}").format(", ".join(citations.FORMATS)))
	body = citations.render(record, fmt, base_url())
	_label, mime, ext = citations.FORMATS[fmt]
	return _text_response(body, mime, f"{item_id}.{ext}" if cint(download) else None)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=10, seconds=60)
def book_text(item_id: str, format: str = "epub"):
	"""The book's text to download: an accessible EPUB 3 (page numbers, language, accessibility
	metadata) or plain text, with corrected pages where people proofread them."""
	from sok_resdesk.catalogue import portal_title
	from sok_resdesk.core import epub
	from sok_resdesk.core.citations import url_for
	from sok_resdesk.core.normalize import lang_tag
	from sok_resdesk.ingest import fetch_pages

	record = get_record(item_id)
	if not record:
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	if not access.can_read(record.get("visibility")):
		frappe.throw(_("Log in to download this book's text."), frappe.PermissionError)
	fmt = (format or "epub").lower()
	if fmt not in ("epub", "txt"):
		frappe.throw(_("Unknown format. Use epub or txt."))
	pages = fetch_pages(item_id) if record.get("has_page_text") else []
	if not epub.text_pages(pages):
		frappe.throw(_("This book has no text yet."))
	url = url_for({k: v for k, v in record.items() if k != "page_url"}, base_url())
	if fmt == "txt":
		return _text_response(epub.plain_text(record, pages, url), "text/plain", f"{item_id}.txt")
	body = epub.build(record, pages, lang_tag(record.get("language")), url, portal_title())
	resp = Response(body, content_type="application/epub+zip")
	resp.headers["Content-Disposition"] = f'attachment; filename="{item_id}.epub"'
	return resp


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=60, seconds=60)
def cite_many(item_ids, format: str = "bibtex"):
	"""Several records in one file: a reading list or a shared bibliography."""
	ids = _loads(item_ids, [])
	if isinstance(ids, str):
		ids = [ids]
	ids = list(dict.fromkeys(ids))[:MAX_BATCH]
	records = [r for r in (get_record(i) for i in ids) if r]
	fmt = format.lower()
	if fmt not in citations.FORMATS:
		frappe.throw(_("Unknown format"))
	if fmt in ("csl-json", "csl", "csljson"):
		body = json.dumps([citations.to_csl(r, base_url()) for r in records], ensure_ascii=False, indent=2)
	else:
		sep = "\n" if fmt in ("bibtex", "biblatex", "ris") else "\n\n"
		body = sep.join(citations.render(r, fmt, base_url()) for r in records)
	_label, mime, ext = citations.FORMATS[fmt]
	return _text_response(body, mime, f"reading-list.{ext}")


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=30, seconds=60)
def marcxml(item_ids):
	"""MARCXML for one or more records, ready for Koha's "Stage MARC records for import"."""
	ids = _loads(item_ids, [])
	if isinstance(ids, str):
		ids = [ids]
	records = [r for r in (get_record(i) for i in list(dict.fromkeys(ids))[:MAX_BATCH]) if r]
	return _text_response(
		marc.to_marcxml_collection(records, base_url()), "application/marcxml+xml", "records.xml"
	)


@frappe.whitelist()
def marcxml_all(profile: str | None = None):
	"""Whole catalogue (or one ingest profile) as MARCXML. Staff only."""
	frappe.only_for(("System Manager", "ResDesk Manager", "ResDesk Cataloguer"))
	filters = {"published": 1}
	if profile:
		filters["ingest_profile"] = profile
	names = frappe.get_all("RD Item", filters=filters, pluck="name")
	records = [get_record(n, check_access=False) for n in names]
	return _text_response(
		marc.to_marcxml_collection([r for r in records if r], base_url()),
		"application/marcxml+xml",
		f"resdesk-{profile or 'all'}.xml",
	)


@frappe.whitelist(allow_guest=True, methods=["GET", "HEAD"])
@rate_limit(limit=600, seconds=60)
def file(item_id: str, name: str):
	"""A local-only book's PDF or cover image, streamed from its folder or its book server.

	Only the two files recorded on the item are ever served (or, for a book served from our
	preservation copy, its PDF there); PDFs only for Open items.
	Supports HTTP range requests, so PDF viewers can open large books page by page.
	"""
	from werkzeug.utils import send_file

	from sok_resdesk.core.folder import HttpStore
	from sok_resdesk.local_source import store_for_item

	doc = frappe.db.get_value(
		"RD Item",
		item_id,
		[
			"name",
			"published",
			"source",
			"access_status",
			"local_pdf",
			"local_thumb",
			"visibility",
			"served_from_copy",
		],
		as_dict=True,
	)
	if doc and doc.published and doc.served_from_copy:
		# a book archive.org no longer serves: its PDF from our preservation copy
		from sok_resdesk.preservation import copy_pdf

		found = copy_pdf(item_id)
		if not found or name != found[0] or not access.can_find(doc.visibility):
			raise frappe.PageDoesNotExistError
		if doc.access_status != "Open" or not access.can_read(doc.visibility):
			raise frappe.PermissionError
		return send_file(
			found[1], frappe.local.request.environ, conditional=True, max_age=86400, download_name=name
		)
	if (
		not doc
		or not doc.published
		or doc.source != "Local"
		or name not in {doc.local_pdf, doc.local_thumb} - {"", None}
	):
		raise frappe.PageDoesNotExistError
	if not access.can_find(doc.visibility):
		raise frappe.PageDoesNotExistError
	if name == doc.local_pdf and (doc.access_status != "Open" or not access.can_read(doc.visibility)):
		raise frappe.PermissionError
	store = store_for_item(frappe.get_doc("RD Item", item_id))
	if store is None:
		raise frappe.PageDoesNotExistError
	loc = frappe.db.get_value("RD Item", item_id, "local_path")
	if isinstance(store, HttpStore):
		# Stream through Research Desk so the book server can stay on a private network.
		headers = {}
		if frappe.local.request.headers.get("Range"):
			headers["Range"] = frappe.local.request.headers["Range"]
		upstream = store.session.get(store.public_url(loc, name), headers=headers, stream=True, timeout=60)
		if upstream.status_code not in (200, 206):
			raise frappe.PageDoesNotExistError
		passthrough = {
			k: v
			for k, v in upstream.headers.items()
			if k.lower()
			in ("content-type", "content-length", "content-range", "accept-ranges", "last-modified", "etag")
		}
		passthrough["Cache-Control"] = "public, max-age=86400"
		return Response(upstream.iter_content(64 * 1024), status=upstream.status_code, headers=passthrough)
	path = store.file_path(loc, name)
	if not path:
		raise frappe.PageDoesNotExistError
	return send_file(path, frappe.local.request.environ, conditional=True, max_age=86400, download_name=name)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def stats():
	seen = f"published=1 and {access.sql_condition()}"  # what this visitor can find
	counts = {
		"items": frappe.db.sql(f"select count(*) from `tabRD Item` where {seen}")[0][0],
		"creators": frappe.db.count("RD Creator"),
		"with_fulltext": frappe.db.sql(f"select count(*) from `tabRD Item` where {seen} and has_fulltext=1")[
			0
		][0],
		"languages": frappe.db.sql(
			f"select language_label, count(*) from `tabRD Item` where {seen} group by language_label order by 2 desc"
		),
	}
	try:
		client = MeiliClient.from_settings()
		idx = client.stats().get("indexes", {})
		counts["indexed_pages"] = idx.get(client.pages, {}).get("numberOfDocuments", 0)
		counts["search"] = "ok"
	except SearchError:
		counts["search"] = "unavailable"
	return counts
