"""SRU 1.2 for the catalogue (core/sru.py has the format).

    /sru                                       the explain record: what this server holds
    /sru?operation=searchRetrieve&query=…      search by title, author, subject, identifier, date, language
          &startRecord=1&maximumRecords=10&recordSchema=marcxml|dc

Answered before Frappe routes the request (like OPDS and IIIF), for the records OAI-PMH exposes
(Settings → Sharing & Identifiers → OAI-PMH Scope), so a harvester and a Z39.50 gateway see the
same catalogue. Switched off with Settings → Features → Sharing metadata.
"""

from __future__ import annotations

from urllib.parse import urlparse

import frappe
from werkzeug.wrappers import Response

from sok_resdesk import features
from sok_resdesk.catalogue import base_url, portal_title
from sok_resdesk.core import marc, oai, sru
from sok_resdesk.iiif import Served
from sok_resdesk.oai import _record, _where

SCHEMA_ALIASES = {
	"marcxml": "marcxml",
	"info:srw/schema/1/marcxml-v1.1": "marcxml",
	"dc": "dc",
	"oai_dc": "dc",
	"info:srw/schema/1/dc-v1.1": "dc",
}


def _xml(body: str) -> Response:
	resp = Response(body, content_type="text/xml; charset=utf-8")
	resp.headers["Access-Control-Allow-Origin"] = "*"
	resp.headers["Cache-Control"] = "public, max-age=300"
	return resp


def explain() -> Response:
	base = base_url()
	url = urlparse(base)
	port = str(url.port or (443 if url.scheme == "https" else 80))
	return _xml(
		sru.explain_response(
			host=url.hostname or "",
			port=port,
			database="sru",
			title=portal_title(),
			description=frappe._("The catalogue of {0}").format(portal_title()),
		)
	)


def search(args) -> Response:
	query = (args.get("query") or "").strip()
	if not query:
		return _xml(sru.diagnostics_response("searchRetrieve", [sru.Diagnostic(7, "query")]))
	schema = SCHEMA_ALIASES.get((args.get("recordSchema") or "marcxml").strip())
	if not schema:
		return _xml(
			sru.diagnostics_response("searchRetrieve", [sru.Diagnostic(66, args.get("recordSchema"))])
		)
	try:
		tree = sru.parse(query)
		condition, params = sru.to_sql(tree)
	except sru.Diagnostic as e:
		return _xml(sru.diagnostics_response("searchRetrieve", [e]))
	start = sru.clamp(args.get("startRecord"), 1, 10**9, minimum=1)
	maximum = sru.clamp(args.get("maximumRecords"), sru.DEFAULT_RECORDS, sru.MAX_RECORDS)
	where = f"{_where()} and {condition}"
	total = frappe.db.sql(f"select count(*) from `tabRD Item` where {where}", params)[0][0]
	if total and start > total:
		return _xml(sru.diagnostics_response("searchRetrieve", [sru.Diagnostic(61, str(start))]))
	names = (
		frappe.db.sql_list(
			f"select name from `tabRD Item` where {where} order by modified desc, name asc limit %s offset %s",
			[*params, maximum, start - 1],
		)
		if maximum
		else []
	)
	base = base_url()
	records = []
	for name in names:
		item = _record(name)
		records.append(
			oai.dc_record(item, base)
			if schema == "dc"
			else marc.to_marcxml_record(item, base, with_namespace=True)
		)
	nxt = start + len(names) if names and start + len(names) <= total else None
	return _xml(
		sru.search_response(
			total=total,
			records=records,
			schema=schema,
			start=start,
			next_start=nxt,
			query=query,
			maximum=maximum,
		)
	)


def route(args) -> Response:
	operation = (args.get("operation") or "").strip() or (
		"searchRetrieve" if args.get("query") else "explain"
	)
	if operation == "explain":
		return explain()
	if operation == "searchRetrieve":
		return search(args)
	return _xml(sru.diagnostics_response("searchRetrieve", [sru.Diagnostic(6, operation)]))


def before_request() -> None:
	"""hooks: answer /sru here, so the address is plain."""
	request = getattr(frappe, "request", None)
	path = (request.path or "") if request else ""
	if not request or path.rstrip("/") != "/sru":
		return
	if request.method not in ("GET", "HEAD"):
		raise Served(Response("GET only\n", status=405, content_type="text/plain"))
	if not features.on("sharing"):
		raise Served(
			Response("SRU is switched off for this library\n", status=404, content_type="text/plain")
		)
	raise Served(route(request.args))
