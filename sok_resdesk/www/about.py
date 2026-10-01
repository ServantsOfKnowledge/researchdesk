import frappe

from sok_resdesk import about, access

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	page = about.context()
	if not page.enabled:
		# switched off in the Desk: visitors go to the library instead of a "not found" page
		from sok_resdesk.portal import library_url

		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	context.update(page)
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.metatags = {
		"title": page.title,
		"description": page.description,
		"image": page.image or page.logo,
	}
	return context
