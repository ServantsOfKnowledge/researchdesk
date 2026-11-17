"""Books like this one, for the book page: more by the same author, the same series, similar subjects
and similar titles. They come from the search engine's own book records, so a reader sees only what
they could find by searching, and the answer is kept for an hour."""

from __future__ import annotations

import hashlib

import frappe
from frappe import _

from sok_resdesk import access
from sok_resdesk.search import MeiliClient, SearchError, _quote, doc_id

PER_GROUP = 6
AUTHORS = 2  # the first authors of a book get a row each
KEEP = ["item_id", "title", "alt_title", "creators", "year", "language_label", "thumbnail_url"]
TTL = 3600


def related(item_id: str, per_group: int = PER_GROUP) -> list[dict]:
	"""[{title, books: [{item_id, title, creators, year, language, thumbnail, url}]}], best groups first."""
	allowed = access.search_filter("books")
	if allowed == "":
		return []
	client = MeiliClient.from_settings()
	key = f"resdesk:related:{client.books}:{item_id}:{hashlib.sha1((allowed or '').encode()).hexdigest()[:8]}"
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	try:
		me = client._req("GET", f"/indexes/{client.books}/documents/{doc_id(item_id)}")
		groups = _groups(client, item_id, me, allowed, per_group)
	except SearchError:
		return []  # not in the search engine (yet), or it is away: nothing to suggest
	frappe.cache.set_value(key, groups, expires_in_sec=TTL)
	return groups


def queries_for(me: dict, item_id: str, allowed: str | None) -> list[tuple[str, dict]]:
	"""(heading, search body) for each kind of likeness the book has something to say about."""
	not_me = f"item_id != {_quote(item_id)}"
	same_language = [f"language_label = {_quote(me['language_label'])}"] if me.get("language_label") else []
	base = [not_me] + ([allowed] if allowed else [])
	out: list[tuple[str, dict]] = []
	for author in [a for a in (me.get("creators") or []) if a][:AUTHORS]:
		out.append(
			(_("More by {0}").format(author), {"q": "", "filter": [f"creators = {_quote(author)}", *base]})
		)
	if me.get("series"):
		out.append(
			(
				_("In the same series"),
				{"q": f'"{me["series"]}"', "attributesToSearchOn": ["series"], "filter": base},
			)
		)
	subjects = [s for s in (me.get("subjects") or []) if s][:5]
	if subjects:
		out.append(
			(
				_("On similar subjects"),
				{
					"q": " ".join(subjects),
					"attributesToSearchOn": ["subjects"],
					"matchingStrategy": "frequency",
					"filter": same_language + base,
				},
			)
		)
	if me.get("title"):
		out.append(
			(
				_("With similar titles"),
				{
					"q": me["title"],
					"attributesToSearchOn": ["title", "alt_title", "description"],
					"matchingStrategy": "frequency",
					"filter": same_language + base,
				},
			)
		)
	return out


def _groups(client: MeiliClient, item_id: str, me: dict, allowed, per_group: int) -> list[dict]:
	asks = queries_for(me, item_id, allowed)
	if not asks:
		return []
	body = {
		"queries": [
			{
				"indexUid": client.books,
				"limit": per_group * 2,  # some will already be shown in an earlier group
				"attributesToRetrieve": KEEP,
				**ask,
			}
			for _heading, ask in asks
		]
	}
	results = client._req("POST", "/multi-search", json=body).get("results", [])
	return merge([h for h, _a in asks], [r.get("hits", []) for r in results], item_id, per_group)


def merge(headings: list[str], hit_lists: list[list[dict]], item_id: str, per_group: int) -> list[dict]:
	"""Each book once, in the first group that has it; groups with nothing left are dropped."""
	seen = {item_id}
	groups = []
	for heading, hits in zip(headings, hit_lists, strict=False):
		books = []
		for h in hits:
			if h["item_id"] in seen or len(books) >= per_group:
				continue
			seen.add(h["item_id"])
			books.append(
				{
					"item_id": h["item_id"],
					"title": h.get("title") or h["item_id"],
					"creators": h.get("creators") or [],
					"year": h.get("year"),
					"language": h.get("language_label"),
					"thumbnail": h.get("thumbnail_url") or "",
					"url": f"/library/item/{h['item_id']}",
				}
			)
		if books:
			groups.append({"title": heading, "books": books})
	return groups
