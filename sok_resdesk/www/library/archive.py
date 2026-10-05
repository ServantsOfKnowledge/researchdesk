import frappe

from sok_resdesk import access, archival
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""The archive's fonds and collections (archival.py): the top of the described hierarchy."""
	access.require_login_for_portal()
	from sok_resdesk.translations import tr

	s = settings()
	units = archival.top_units()
	if not units and not archival.features.on("archival"):
		raise frappe.PageDoesNotExistError
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = frappe._("Archives") + f" · {context.portal_title}"
	context.units = units
	context.metatags = {
		"title": context.title,
		"description": frappe._("The archive's papers, described as fonds, series, file and item."),
	}
	return context
