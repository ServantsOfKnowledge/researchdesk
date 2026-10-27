import frappe

from sok_resdesk import about, access, sitepages
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	page = sitepages.get(frappe.form_dict.get("slug"))
	if not page:
		raise frappe.PageDoesNotExistError
	if page.members_only and not access.is_member():
		if frappe.session.user != "Guest":
			raise frappe.PermissionError
		frappe.local.flags.redirect_location = access.login_url(sitepages.route(page.slug))
		raise frappe.Redirect
	from sok_resdesk.translations import tr

	portal = tr(settings().portal_title) or "SOK Research Desk"
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = portal
	context.page_title = page.title
	context.title = f"{page.title} · {portal}"
	context.body = about.rich(page.body)
	context.draft = not page.published
	context.metatags = {"title": page.title, "description": page.summary or ""}
	return context
