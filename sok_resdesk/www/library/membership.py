import frappe

from sok_resdesk import access, features, patrons
from sok_resdesk.core import signup as rules
from sok_resdesk.portal import library_url

no_cache = 1


def get_context(context):
	"""Become a member with the number on your ID card (or, signed in, link the account to the roster)."""
	if not features.on("lending"):
		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	if frappe.session.user != "Guest" and frappe.db.exists("RD Patron", {"user": frappe.session.user}):
		frappe.local.flags.redirect_location = "/library/loans"
		raise frappe.Redirect
	from sok_resdesk.catalogue import settings
	from sok_resdesk.translations import tr

	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = frappe._("Become a member") + " · " + context.portal_title
	context.signed_in = frappe.session.user != "Guest"
	context.open = bool(patrons.default_category())
	context.min_password = rules.MIN_PASSWORD
	context.login_url = access.login_url("/library/membership")
	context.metatags = {"title": context.title}
	return context
