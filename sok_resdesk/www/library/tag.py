import frappe

from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""Every page readers' public notes tagged with one tag."""
	from sok_resdesk.annotations import by_book, notes_tagged

	tag = (frappe.form_dict.get("tag") or "").strip()[:100]
	if not tag:
		raise frappe.DoesNotExistError
	notes = notes_tagged(tag)
	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = s.portal_title or "SOK Research Desk"
	context.tag = tag
	context.books = by_book(notes)
	context.count = len(notes)
	context.title = f"#{tag} · {context.portal_title}"
	context.metatags = {"title": context.title}
	if not notes:
		context.metatags["robots"] = "noindex"
	return context
