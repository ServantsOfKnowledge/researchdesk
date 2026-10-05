import frappe

from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""A Wikidata item (a person, place, work or idea) and every page readers' public notes say
	is about it."""
	from sok_resdesk.annotations import by_book, describe, notes_about
	from sok_resdesk.core import wikidata

	q = wikidata.qid(frappe.form_dict.get("entity"))
	if not q:
		raise frappe.DoesNotExistError
	notes = notes_about(q)
	named = next((n for n in notes if n.get("entity_label")), None)
	info = {"label": named["entity_label"], "description": named.get("entity_description")} if named else None
	info = info or describe([q]).get(q) or {"label": q, "description": ""}
	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = s.portal_title or "SOK Research Desk"
	context.entity = q
	context.label = info.get("label") or q
	context.description = info.get("description") or ""
	context.wikidata_url = wikidata.page_url(q)
	context.books = by_book(notes)
	context.count = len(notes)
	# a person the catalogue's authors are matched to (Desk → Authorities): their books
	from sok_resdesk.authority import creator_books

	context.written = creator_books(q)
	context.title = f"{context.label} · {context.portal_title}"
	context.metatags = {"title": context.title, "description": context.description}
	if not notes and not context.written:
		context.metatags["robots"] = "noindex"
	return context
