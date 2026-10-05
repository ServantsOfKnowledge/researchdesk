"""Findable and safe: what search engines and browsers are told about the portal.

* **Search engines** get a ``robots.txt`` that keeps them out of the Desk, the API and the pages
  that only make sense to a person (proofreading, notes, search results with filters), and a
  **sitemap** of every published book and collection (an index of parts of 40,000 addresses: the
  protocol's limit is 50,000). Every page says what it is: a description, an image and its
  canonical address, and, when the portal is offered in other languages, the same page in each
  of them (``hreflang``, ``?_lang=kn``).
* **Browsers** get security headers on every page Research Desk makes: no sniffing of content
  types, no framing by other sites, no plugins, a strict referrer, HSTS over HTTPS.

Pure Python so it is unit-tested directly.
"""

from __future__ import annotations

import re
from html import escape
from urllib.parse import quote, urlencode

SITEMAP_PART = 40_000  # addresses per sitemap part (the protocol allows 50,000)
DESCRIPTION = 200  # characters: what search results show of a description

# never crawled: the Desk, the API (except what readers download), people's own pages
DISALLOW = (
	"/app",
	"/desk",
	"/api/",
	"/login",
	"/update-password",
	"/library/proofread",
	"/library/notes",
	"/library/withdrawn",
	"/private/",
	"/*?*q=",  # searches: endless combinations of the same books
	"/*?*page=",
)
ALLOW = (
	"/api/method/sok_resdesk.api.cite",  # citation files linked from book pages
	"/api/method/sok_resdesk.api.page_image",
	"/api/method/sok_resdesk.api.file",
)


def robots_txt(base_url: str, extra: str = "") -> str:
	"""The site's robots.txt: our rules, the library's own lines (Website Settings), the sitemap."""
	lines = ["User-agent: *"]
	lines += [f"Allow: {p}" for p in ALLOW]
	lines += [f"Disallow: {p}" for p in DISALLOW]
	out = "\n".join(lines) + "\n"
	if extra.strip():
		out += "\n" + extra.strip() + "\n"
	return out + f"\nSitemap: {base_url.rstrip('/')}/sitemap.xml\n"


def urlset(entries: list[tuple[str, str]]) -> str:
	"""A sitemap: [(address, last changed YYYY-MM-DD)]."""
	rows = "".join(
		f"<url><loc>{escape(loc)}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</url>\n"
		for loc, mod in entries
	)
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n"
	)


def sitemap_index(parts: list[tuple[str, str]]) -> str:
	"""The sitemap index: [(address of a part, last changed)]."""
	rows = "".join(
		f"<sitemap><loc>{escape(loc)}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</sitemap>\n"
		for loc, mod in parts
	)
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</sitemapindex>\n"
	)


def book_url(base_url: str, item_id: str) -> str:
	return f"{base_url.rstrip('/')}/library/item/{quote(item_id, safe='')}"


def describe(record: dict, portal: str = "") -> str:
	"""A book's description for search results and link previews: its own, or one made from
	the catalogue (what it is, who wrote it, when, in what language, that its text is here)."""
	own = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", record.get("description") or "")).strip()
	if len(own) >= 60:
		return _cut(own)
	kind = (record.get("item_type") or "Book").lower()
	parts = [f"A {kind}" if kind != "other" else "A document"]
	creators = [c for c in record.get("creators") or [] if c][:2]
	if creators:
		parts.append("by " + " and ".join(creators))
	if record.get("year"):
		parts.append(f"from {record['year']}")
	if record.get("language_label") and record["language_label"] != "Unknown":
		parts.append(f"in {record['language_label']}")
	text = " ".join(parts) + "."
	if record.get("publisher"):
		text += f" Published by {record['publisher']}."
	if record.get("has_page_text"):
		text += " Read it and search inside its text, page by page"
		text += f", at {portal}." if portal else "."
	if own:
		text = own + " " + text
	return _cut(text)


def _cut(text: str, limit: int = DESCRIPTION) -> str:
	if len(text) <= limit:
		return text
	cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
	return cut + "…"


def alternates(
	base_url: str, path: str, langs: list[str], query: dict | None = None
) -> list[tuple[str, str]]:
	"""[(hreflang, address)] for one page in each portal language, and x-default (English)."""
	if not langs:
		return []
	base = base_url.rstrip("/") + "/" + path.strip("/")
	query = {k: v for k, v in (query or {}).items() if k != "_lang"}

	def address(lang=""):
		q = dict(query, **({"_lang": lang} if lang else {}))
		return base + ("?" + urlencode(q) if q else "")

	return [("x-default", address()), ("en", address("en"))] + [(lang, address(lang)) for lang in langs]


def head_links(canonical: str, alternate: list[tuple[str, str]], noindex: bool = False) -> str:
	out = [f'<link rel="canonical" href="{escape(canonical)}">']
	out += [
		f'<link rel="alternate" hreflang="{escape(lang)}" href="{escape(url)}">' for lang, url in alternate
	]
	if noindex:
		out.append('<meta name="robots" content="noindex,follow">')
	return "\n".join(out)


def website_json_ld(base_url: str, name: str, description: str = "") -> dict:
	"""The home page's schema.org WebSite, with the search box search engines can show."""
	base = base_url.rstrip("/")
	data = {
		"@context": "https://schema.org",
		"@type": "WebSite",
		"name": name,
		"url": base + "/",
		"potentialAction": {
			"@type": "SearchAction",
			"target": {"@type": "EntryPoint", "urlTemplate": base + "/library?q={search_term_string}"},
			"query-input": "required name=search_term_string",
		},
	}
	if description:
		data["description"] = description
	return data


def security_headers(https: bool, desk: bool) -> dict[str, str]:
	"""Headers for every page Research Desk makes. The Desk needs its inline scripts, so the
	content policy limits what can't break it: who may frame us, plugins, the base address and
	where forms may post."""
	headers = {
		"X-Content-Type-Options": "nosniff",
		"Referrer-Policy": "strict-origin-when-cross-origin",
		"X-Frame-Options": "SAMEORIGIN",
		"Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
		"Content-Security-Policy": "frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
		+ ("" if desk else "; form-action 'self'"),
		"Cross-Origin-Opener-Policy": "same-origin-allow-popups",
	}
	if https:
		headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
	return headers
