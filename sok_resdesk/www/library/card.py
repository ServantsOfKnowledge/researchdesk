import frappe
from frappe import _

from sok_resdesk import access, features, patrons
from sok_resdesk.portal import library_url

no_cache = 1


def get_context(context):
	"""A member's ID card: their own, or (staff) the cards of the numbers asked for."""
	if not features.on("lending"):
		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/card")
		raise frappe.Redirect
	cards = patrons.cards_for(frappe.form_dict.get("patron") or "")
	if not cards:
		raise frappe.PageDoesNotExistError
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0, "no_header": 1})
	context.cards = cards
	context.title = _("ID card")
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
