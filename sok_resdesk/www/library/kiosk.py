import frappe
from frappe import _

from sok_resdesk import access, features
from sok_resdesk.kiosk import ROLE
from sok_resdesk.portal import library_url

no_cache = 1


def get_context(context):
	"""The self-service kiosk: card and PIN, then borrow. Only the kiosk's own account (or a manager) sees it."""
	if not features.on("lending"):
		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/kiosk")
		raise frappe.Redirect
	from sok_resdesk.catalogue import settings
	from sok_resdesk.translations import tr

	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = _("Borrow a book") + " · " + context.portal_title
	context.allowed = bool(set(frappe.get_roles()) & ({ROLE} | set(access.MANAGER_ROLES)))
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
