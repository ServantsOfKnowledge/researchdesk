"""The About page (/about): an introduction to the library, edited in the Desk (RD About Page)."""

from __future__ import annotations

import re

import frappe
from frappe import _

ROUTE = "/about"

# Starting content, written once (after install or the upgrade that brings the page) so a new
# library has a sensible page to edit rather than an empty one.
DEFAULT_STEPS = [
	(
		"Search",
		"Type a word, a title, an author or a subject. Choose **Inside the text** to search the words on "
		"every page of every book, in Kannada, English and the other languages of the collection.",
		"/",
		"Start searching",
	),
	(
		"Read",
		"Open a book to read it page by page, and search inside it. The scans are kept safe on the "
		"Internet Archive.",
		"",
		"",
	),
	(
		"Cite",
		"Every book has ready-made citations (BibTeX, RIS, APA, MLA, Chicago and more) and works with "
		"Zotero and other reference managers.",
		"",
		"",
	),
	(
		"Keep a reading list",
		"Add books to your list as you go, then export it as a bibliography or share it as a link.",
		"",
		"",
	),
	(
		"Browse collections",
		"Books grouped by subject, place, publisher or the library they came from.",
		"/library/collections",
		"See the collections",
	),
]
DEFAULT_HIGHLIGHTS = [
	(
		"Search inside every page",
		"Not only titles and authors: the full text of each digitised book is searchable.",
		"",
		"",
	),
	(
		"Open and citable",
		"Each book has a stable address and the details researchers need to cite it.",
		"",
		"",
	),
	(
		"For libraries too",
		"Catalogue records for Koha and other library systems through OAI-PMH and MARCXML.",
		"/library/help",
		"How it works",
	),
]


def safe_link(link: str) -> bool:
	"""A page of this site, or a web address: no javascript: or other schemes."""
	link = (link or "").strip()
	return (link.startswith("/") and not link.startswith("//")) or bool(re.match(r"https?://", link, re.I))


def ensure_defaults() -> None:
	"""Fill an untouched About page with starting content (once)."""
	if frappe.db.get_default("resdesk_about_set_up"):
		return
	doc = frappe.get_single("RD About Page")
	title = frappe.db.get_single_value("RD Settings", "portal_title") or "This library"
	if not doc.intro:
		doc.intro = (
			f"<p><strong>{frappe.utils.escape_html(title)}</strong> is an open research library of digitised "
			"books. Search the full text of every page, read the books online, and cite them in your work.</p>"
			"<p>It is free for students, researchers, teachers and everyone curious about the books.</p>"
		)
	if not doc.steps:
		for t, text, link, label in DEFAULT_STEPS:
			doc.append("steps", {"title": t, "text": text, "link": link, "link_label": label})
	if not doc.highlights:
		for t, text, link, label in DEFAULT_HIGHLIGHTS:
			doc.append("highlights", {"title": t, "text": text, "link": link, "link_label": label})
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.set_default("resdesk_about_set_up", "1")


def sync_top_bar(doc) -> None:
	"""The About link in the portal's top bar: after Library, with the page's label; gone when off."""
	ws = frappe.get_single("Website Settings")
	items = list(ws.top_bar_items)
	mine = [i for i in items if (i.url or "").rstrip("/") == ROUTE]
	label = (doc.nav_label or "").strip() or _("About")
	changed = False
	if doc.enabled:
		if mine:
			if mine[0].label != label:
				mine[0].label = label
				changed = True
		else:
			after = next(
				(n for n, i in enumerate(items) if (i.url or "").rstrip("/") in ("/library", "")),
				len(items) - 1,
			)
			row = ws.append("top_bar_items", {"label": label, "url": ROUTE})
			ws.top_bar_items.remove(row)
			ws.top_bar_items.insert(after + 1, row)
			changed = True
	elif mine:
		for i in mine:
			ws.top_bar_items.remove(i)
		changed = True
	if changed:
		for n, i in enumerate(ws.top_bar_items, 1):
			i.idx = n
		ws.flags.ignore_permissions = True
		ws.save()


def inline(text: str) -> str:
	"""Plain text with **bold**, safe to put in the page."""
	html = frappe.utils.escape_html(text or "")
	return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html).replace("\n", "<br>")


def rich(html: str) -> str:
	"""Text Editor content, without scripts or event handlers."""
	if not html or not re.sub(r"<[^>]+>|&nbsp;|\s", "", html) and "<img" not in html:
		return ""
	try:
		from frappe.utils.html_utils import sanitize_html

		return sanitize_html(html, linkify=False)
	except Exception:
		return frappe.utils.escape_html(re.sub(r"<[^>]+>", " ", html))


def _items(rows) -> list[frappe._dict]:
	from sok_resdesk.translations import tr

	return [
		frappe._dict(
			title=tr(r.title),
			text=inline(tr(r.text)),
			link=r.link if r.link and safe_link(r.link) else "",
			link_label=tr(r.link_label) or _("More") + " →",
		)
		for r in rows
		if r.title
	]


def numbers() -> list[tuple[int, str]]:
	"""What the library holds, as this visitor can see it."""
	from sok_resdesk import access

	seen = f"published=1 and {access.sql_condition()}"
	books = frappe.db.sql(f"select count(*) from `tabRD Item` where {seen}")[0][0]
	languages = frappe.db.sql(
		f"select count(distinct language_label) from `tabRD Item` where {seen} and ifnull(language_label, '') != ''"
	)[0][0]
	collections = frappe.db.count("RD Collection", {"published": 1})
	pages = 0
	try:
		from sok_resdesk.search import MeiliClient

		client = MeiliClient.from_settings()
		pages = client.stats().get("indexes", {}).get(client.pages, {}).get("numberOfDocuments", 0)
	except Exception:
		pass
	out = [(books, _("books"))]
	if pages:
		out.append((pages, _("pages of searchable text")))
	if collections:
		out.append((collections, _("collections")))
	if languages:
		out.append((languages, _("languages")))
	return out


def context() -> frappe._dict:
	"""Everything www/about.html shows."""
	from sok_resdesk.catalogue import settings
	from sok_resdesk.portal import library_url
	from sok_resdesk.translations import tr

	doc = frappe.get_cached_doc("RD About Page")
	s = settings()
	portal = tr(s.portal_title) or "SOK Research Desk"
	ctx = frappe._dict(
		enabled=bool(doc.enabled),
		portal_title=portal,
		headline=tr(doc.headline) or portal,
		tagline=tr(doc.tagline) or "",
		intro=rich(tr(doc.intro)),
		image=doc.hero_image or "",
		buttons=[
			frappe._dict(label=label, link=link, primary=primary)
			for label, link, primary in (
				(tr(doc.primary_label), doc.primary_link or library_url(), True),
				(tr(doc.secondary_label), doc.secondary_link, False),
			)
			if label and link and safe_link(link)
		],
		numbers=numbers() if doc.show_stats else [],
		steps_title=tr(doc.steps_title) or "",
		steps=_items(doc.steps),
		highlights_title=tr(doc.highlights_title) or "",
		highlights=_items(doc.highlights),
		body_title=tr(doc.body_title) or "",
		body=rich(tr(doc.body)),
		title=tr(doc.page_title) or _("About {0}").format(portal),
		description=tr(doc.meta_description) or tr(doc.tagline) or tr(s.portal_tagline),
		logo=s.portal_logo or "",
	)
	if doc.show_collections:
		from sok_resdesk.portal import collection_cards

		ctx.collections = [c for c in collection_cards() if c.featured][:8]
	else:
		ctx.collections = []
	return ctx
