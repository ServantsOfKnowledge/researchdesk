import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""About me: a short, optional form for readers and organisations."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/profile")
		raise frappe.Redirect
	s = settings()
	context.update(
		{
			"no_cache": 1,
			"full_width": 1,
			"show_sidebar": 0,
			"portal_title": s.portal_title or "SOK Research Desk",
		}
	)
	context.title = frappe._("About me") + f" · {context.portal_title}"
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
