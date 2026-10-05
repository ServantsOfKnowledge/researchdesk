"""OPDS feeds of the library (core/opds.py has the format).

    /opds                       the start: newest books, collections, search
    /opds/new[?page=2]          the newest books
    /opds/collections           the collections
    /opds/collection/<name>     one collection's books
    /opds/search?q=             a search by title, author or subject
    /opds/opensearch.xml        the search description for reader apps

Answered before Frappe routes the request (like the IIIF addresses), under the same rule as
the portal: a book guests cannot find is not listed; one they can find but not read is listed
without its download. Switched off with Settings → Features → Sharing metadata.
"""

from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe.utils import cint
from werkzeug.wrappers import Response

from sok_resdesk import access, features
from sok_resdesk.catalogue import base_url, portal_title
from sok_resdesk.core import opds
from sok_resdesk.iiif import Served

FIELDS = [
	"name",
	"title",
	"creator_display",
	"language",
	"description",
	"modified",
	"year",
	"thumbnail_url",
	"local_thumb",
	"local_pdf",
	"local_files",
	"source",
	"access_status",
	"visibility",
	"on_archive_org",
]


def _iso(value) -> str:
	return (
		frappe.utils.get_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ") if value else "1970-01-01T00:00:00Z"
	)


def _book(row, base: str) -> dict:
	files = []
	if row.source == "Local" and row.access_status == "Open" and access.can_read(row.visibility):
		names = list(dict.fromkeys([row.local_pdf, *(row.local_files or "").splitlines()]))
		files = [
			(
				f"{base}/api/method/sok_resdesk.api.file?item_id={quote(row.name, safe='')}&name={quote(n, safe='')}",
				n,
			)
			for n in names
			if n
		]
	cover = ""
	if row.source == "Local" and row.local_thumb:
		cover = f"{base}/api/method/sok_resdesk.api.file?item_id={quote(row.name, safe='')}&name={quote(row.local_thumb, safe='')}"
	elif row.thumbnail_url:
		cover = row.thumbnail_url if row.thumbnail_url.startswith("http") else base + row.thumbnail_url
	return {
		"item_id": row.name,
		"title": row.title,
		"authors": [
			a.strip() for a in (row.creator_display or "").replace(";", "\n").splitlines() if a.strip()
		],
		"language": (row.language or "").split(",")[0].strip(),
		"summary": frappe.utils.strip_html_tags(row.description or ""),
		"updated": _iso(row.modified),
		"year": row.year or "",
		"cover": cover,
		"files": files,
	}


def _listing(title: str, path: str, where: dict, page: int, q: str = "", ids=None) -> Response:
	base = base_url()
	filters = {"published": 1, **where}
	or_filters = None
	if q:
		like = f"%{q}%"
		or_filters = [
			["title", "like", like],
			["creator_display", "like", like],
			["description", "like", like],
		]
	if ids is not None:
		filters["name"] = ("in", ids or ["-"])
	rows = [
		r
		for r in frappe.get_all(
			"RD Item",
			filters=filters,
			or_filters=or_filters,
			fields=FIELDS,
			order_by="modified desc",
			limit_start=(page - 1) * opds.PER_PAGE,
			limit_page_length=opds.PER_PAGE + 1,
		)
		if access.can_find(r.visibility)
	]
	more = len(rows) > opds.PER_PAGE
	rows = rows[: opds.PER_PAGE]
	sep = "&" if "?" in path else "?"
	body = opds.feed(
		base,
		title=title,
		path=path if page == 1 else f"{path}{sep}page={page}",
		kind="acq",
		updated=_iso(rows[0].modified if rows else None),
		entries=[opds.entry(base, _book(r, base)) for r in rows],
		nxt=f"{path}{sep}page={page + 1}" if more else "",
	)
	return _xml(body, opds.ACQ)


def _xml(body: str, type_: str) -> Response:
	resp = Response(body, content_type=f"{type_}; charset=utf-8")
	resp.headers["Access-Control-Allow-Origin"] = "*"
	resp.headers["Cache-Control"] = (
		"private, no-store" if frappe.session.user != "Guest" else "public, max-age=300"
	)
	return resp


def _not_found() -> Response:
	return Response("Not an OPDS address\n", status=404, content_type="text/plain")


def start() -> Response:
	base = base_url()
	entries = [
		opds.nav_entry(base, "Newest books", "/opds/new", "Recently added or changed"),
		opds.nav_entry(base, "Collections", "/opds/collections", "Browse by collection", kind="nav"),
	]
	return _xml(
		opds.feed(base, title=portal_title(), path="/opds", kind="nav", updated=_iso(None), entries=entries),
		opds.NAV,
	)


def collections() -> Response:
	base = base_url()
	rows = frappe.get_all(
		"RD Collection",
		filters={"published": 1},
		fields=["name", "title", "description"],
		order_by="sort_order asc, title asc",
	)
	entries = [
		opds.nav_entry(
			base,
			r.title or r.name,
			f"/opds/collection/{quote(r.name, safe='')}",
			frappe.utils.strip_html_tags(r.description or "")[:300],
		)
		for r in rows
	]
	return _xml(
		opds.feed(
			base,
			title=frappe._("Collections"),
			path="/opds/collections",
			kind="nav",
			updated=_iso(None),
			entries=entries,
		),
		opds.NAV,
	)


def route(path: str, args) -> Response | None:
	parts = [p for p in path.split("/") if p]
	if not parts or parts[0] != "opds":
		return None
	rest = parts[1:]
	page = max(1, cint(args.get("page") or 1))
	if not rest:
		return start()
	if rest == ["opensearch.xml"]:
		return _xml(opds.opensearch(base_url(), portal_title()), "application/opensearchdescription+xml")
	if rest == ["new"]:
		return _listing(frappe._("Newest books"), "/opds/new", {}, page)
	if rest == ["collections"]:
		return collections()
	if rest[0] == "collection" and len(rest) == 2:
		name = rest[1]
		if not frappe.db.exists("RD Collection", {"name": name, "published": 1}):
			return _not_found()
		ids = frappe.db.sql_list(
			"select parent from `tabRD Item Collection` where collection=%s and parenttype='RD Item'", name
		)
		return _listing(name, f"/opds/collection/{quote(name, safe='')}", {}, page, ids=ids)
	if rest == ["search"]:
		q = (args.get("q") or "").strip()[:200]
		return _listing(frappe._("Search: {0}").format(q), f"/opds/search?q={quote(q)}", {}, page, q=q)
	return _not_found()


def before_request() -> None:
	"""hooks: answer /opds… here, so the addresses are plain."""
	request = getattr(frappe, "request", None)
	path = (request.path or "") if request else ""
	if not request or not (path == "/opds" or path.startswith("/opds/")):
		return
	if request.method not in ("GET", "HEAD"):
		raise Served(Response("GET only\n", status=405, content_type="text/plain"))
	if not features.on("sharing"):
		raise Served(
			Response("OPDS is switched off for this library\n", status=404, content_type="text/plain")
		)
	try:
		response = route(path, request.args)
	except frappe.DoesNotExistError:
		response = _not_found()
	if response is not None:
		raise Served(response)
