import frappe

from sok_resdesk import access, features
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""Deposit: a person gives the library their own work (details, licence, files) for review."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/deposit")
		raise frappe.Redirect
	if not features.on("deposit"):
		raise frappe.PageDoesNotExistError
	from sok_resdesk.deposit import DEPOSITORS

	s = settings()
	context.update(
		{
			"no_cache": 1,
			"full_width": 1,
			"show_sidebar": 0,
			"portal_title": s.portal_title or "SOK Research Desk",
			"allowed": bool(set(frappe.get_roles()) & set(DEPOSITORS)),
		}
	)
	context.title = frappe._("Deposit your work") + f" · {context.portal_title}"
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
