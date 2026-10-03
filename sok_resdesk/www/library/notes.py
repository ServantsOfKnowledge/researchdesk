import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""My notes: the reader's notes on every book (and their research groups'), to search, open at
	their page and export with page citations."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/notes")
		raise frappe.Redirect
	s = settings()
	from sok_resdesk.annotations import my_groups

	context.update(
		{
			"no_cache": 1,
			"full_width": 1,
			"show_sidebar": 0,
			"portal_title": s.portal_title or "SOK Research Desk",
			"groups": my_groups(),
		}
	)
	context.title = frappe._("My notes") + f" · {context.portal_title}"
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
