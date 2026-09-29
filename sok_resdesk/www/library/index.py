import frappe

from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.title = s.portal_title or "SoK Research Desk"
	context.portal_title = context.title
	context.tagline = s.portal_tagline or ""
	context.item_count = frappe.db.count("RD Item", {"published": 1})
	context.metatags = {
		"title": context.title,
		"description": context.tagline,
	}
	return context
