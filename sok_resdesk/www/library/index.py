import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	from sok_resdesk.portal import library_url

	request = frappe.local.request
	if request and request.path.rstrip("/") == "/library" and library_url() == "/":
		# the search page lives at /: old /library links (and their searches) land there.
		# 302, not 301: browsers don't remember it, in case the home page changes later
		query = request.query_string.decode()
		frappe.local.flags.redirect_location = "/" + (f"?{query}" if query else "")
		raise frappe.Redirect(302)
	access.require_login_for_portal()
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	from sok_resdesk.translations import tr

	context.title = tr(s.portal_title) or "SOK Research Desk"
	context.portal_title = context.title
	context.tagline = tr(s.portal_tagline)
	from sok_resdesk.portal import item_count

	context.item_count = item_count()
	context.viewer = access.viewer()
	from sok_resdesk import profile

	context.ask_profile = bool(context.viewer.get("logged_in")) and not profile.has_profile()
	context.login_url = access.login_url("/library")
	context.visibilities = access.VISIBILITIES
	from sok_resdesk.portal import collection_cards, facet_labels

	cards = collection_cards()
	context.featured_collections = [c for c in cards if c.featured][:8]
	context.has_collections = bool(cards)
	from sok_resdesk import archival

	context.has_archive = bool(archival.top_units())
	context.facet_labels = facet_labels()
	context.logo = s.portal_logo if s.portal_logo and s.logo_on_home else ""
	context.home_banner = s.home_banner or ""
	context.metatags = {
		"title": context.title,
		"description": context.tagline,
		"image": s.portal_logo or "",
	}
	return context
