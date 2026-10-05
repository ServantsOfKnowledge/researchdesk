"""The portal for search engines (core/seo.py): robots.txt, the sitemap of every book, and on
every portal page its canonical address, the same page in each portal language, and whether a
page should be indexed at all."""

from __future__ import annotations

import json
from urllib.parse import quote

import frappe
from frappe.utils import cint

from sok_resdesk.core import seo as core

SEARCH_ARGS = ("q", "page", "sort", "mode") + (
	"language_label",
	"decade",
	"subjects",
	"creators",
	"collections",
)
PORTAL = ("", "about", "library")


def base_url() -> str:
	from sok_resdesk.catalogue import base_url as base

	return base()


def _portal_path(context) -> str | None:
	request = getattr(frappe.local, "request", None)
	path = (
		context.get("path") or getattr(frappe.local, "path", None) or (request.path if request else "") or ""
	).strip("/")
	return path if path in PORTAL or path.startswith("library/") else None


def website_context(context) -> dict | None:
	"""update_website_context: canonical address, hreflang alternates, noindex for searches,
	and the home page's WebSite description with its search box."""
	path = _portal_path(context)
	if path is None:
		return None
	from sok_resdesk.translations import portal_languages

	base = base_url()
	args = {k: v for k, v in (frappe.form_dict or {}).items() if isinstance(v, str) and not k.startswith("_")}
	searching = any(k in args for k in SEARCH_ARGS)
	# the library's home is / (/library sends people there)
	canonical = context.get("portal_url") or (base + ("/" + path if path not in ("", "library") else "/"))
	try:
		langs = portal_languages()
	except Exception:
		langs = []
	# a search or a filtered list: followed, not indexed (endless combinations of the same books)
	links = core.head_links(
		canonical,
		[] if searching else core.alternates(base, "" if path == "library" else path, langs),
		noindex=searching,
	)
	if path in ("", "library") and not searching:
		s = frappe.get_cached_doc("RD Settings")
		data = core.website_json_ld(base, s.portal_title or "SOK Research Desk", s.portal_tagline or "")
		links += (
			'\n<script type="application/ld+json">'
			+ json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
			+ "</script>"
		)
	return {"head_include": (context.get("head_include") or "") + links}


def closed() -> bool:
	"""A members-only portal (Settings → Readers & Access → Login required): nothing to index."""
	from sok_resdesk.access import guest_mode
	from sok_resdesk.core.access import GUEST_NONE

	return guest_mode() == GUEST_NONE


def robots() -> str:
	if closed():
		return "User-agent: *\nDisallow: /\n"
	extra = frappe.db.get_single_value("Website Settings", "robots_txt") or ""
	return core.robots_txt(base_url(), extra)


def sitemap(part: int = 0) -> str:
	"""The sitemap index (part 0), or one part of the books' addresses (1, 2…)."""
	base = base_url()
	public = {"published": 1, "visibility": "Public"}
	if closed():
		return core.urlset([])
	if not part:
		books = frappe.db.count("RD Item", public)
		parts = max(1, -(-books // core.SITEMAP_PART))
		latest = (
			frappe.db.sql("select max(modified) from `tabRD Item` where published=1 and visibility='Public'")[
				0
			][0]
			or ""
		)
		entries = [(f"{base}/sitemap.xml?part={n}", str(latest)[:10]) for n in range(1, parts + 1)]
		entries.append((f"{base}/sitemap.xml?part=pages", ""))
		return core.sitemap_index(entries)
	if part == "pages":
		entries = [(base + "/", ""), (base + "/library/collections", ""), (base + "/about", "")]
		for name, modified in frappe.get_all(
			"RD Collection", filters={"published": 1}, fields=["name", "modified"], as_list=True
		):
			entries.append((f"{base}/library/collection/{quote(name, safe='')}", str(modified)[:10]))
		return core.urlset(entries)
	start = (cint(part) - 1) * core.SITEMAP_PART
	rows = frappe.get_all(
		"RD Item",
		filters=public,
		fields=["name", "modified"],
		order_by="creation asc",
		limit_start=start,
		limit_page_length=core.SITEMAP_PART,
		as_list=True,
	)
	return core.urlset([(core.book_url(base, name), str(modified)[:10]) for name, modified in rows])
