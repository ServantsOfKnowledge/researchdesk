import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.title = s.portal_title or "SoK Research Desk"
	context.portal_title = context.title
	context.tagline = s.portal_tagline or ""
	context.item_count = frappe.db.sql(
		f"select count(*) from `tabRD Item` where published=1 and {access.sql_condition()}"
	)[0][0]
	context.viewer = access.viewer()
	context.login_url = access.login_url("/library")
	context.visibilities = access.VISIBILITIES
	context.logo = s.portal_logo if s.portal_logo and s.logo_on_home else ""
	context.home_banner = s.home_banner or ""
	context.metatags = {
		"title": context.title,
		"description": context.tagline,
		"image": s.portal_logo or "",
	}
	return context
