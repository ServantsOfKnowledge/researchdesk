import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings
from sok_resdesk.help import portal_page

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	try:
		page = portal_page(frappe.form_dict.get("slug"))
	except frappe.DoesNotExistError:
		raise frappe.PageDoesNotExistError from None
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.portal_title = s.portal_title or "SoK Research Desk"
	context.page = page
	context.title = f"{page['title']} · {context.portal_title}"
	context.viewer = access.viewer()
	context.metatags = {
		"title": page["title"],
		"description": frappe._("Help for readers of {0}").format(context.portal_title),
	}
	return context
