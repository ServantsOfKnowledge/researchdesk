import frappe
from frappe import _

from sok_resdesk import access, features, lending
from sok_resdesk.portal import library_url

no_cache = 1


def get_context(context):
	"""My library: a member's loans, holds, fines and ID card."""
	if not features.on("lending"):
		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/loans")
		raise frappe.Redirect
	from sok_resdesk.catalogue import settings
	from sok_resdesk.translations import tr

	s = settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = _("My library") + " · " + context.portal_title
	member = lending.patron_of()
	context.state = (
		"none"
		if not member
		else ("pending" if member.status in ("Pending", "Listed", "Rejected") else "member")
	)
	context.status = member.status if member else ""
	context.me = lending.snapshot(member.name) if context.state == "member" else None
	context.has_pin = lending.has_pin(member.name) if context.state == "member" else False
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
