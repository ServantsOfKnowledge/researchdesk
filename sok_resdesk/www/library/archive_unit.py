import frappe

from sok_resdesk import access, archival
from sok_resdesk.catalogue import base_url, settings

no_cache = 1

# the ISAD(G) fields shown, in order: (field, label)
SHOWN = [
	("creator", "Creator"),
	("date_text", "Dates"),
	("extent", "Extent"),
	("language", "Language of the material"),
	("physical", "Physical characteristics"),
	("admin_history", "Administrative or biographical history"),
	("custodial_history", "Custodial history"),
	("scope_content", "Scope and content"),
	("arrangement", "System of arrangement"),
	("access_conditions", "Conditions governing access"),
	("reproduction_conditions", "Conditions governing reproduction"),
	("finding_aids", "Finding aids"),
	("related_materials", "Related units of description"),
	("notes", "Notes"),
]


def get_context(context):
	"""One unit of archival description: its fields, where it sits, what is under it and the
	digitised items attached to it."""
	access.require_login_for_portal()
	from sok_resdesk.translations import tr

	page = archival.unit_page(frappe.form_dict.get("unit"))
	if not page:
		raise frappe.PageDoesNotExistError
	unit, s = page["unit"], settings()
	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = f"{unit['title']} · {context.portal_title}"
	context.page = page
	context.unit = unit
	context.rows = [(frappe._(label), unit.get(f)) for f, label in SHOWN if unit.get(f)]
	context.portal_url = f"{base_url()}/library/archive/{unit['name']}"
	context.metatags = {
		"title": context.title,
		"description": (unit.get("scope_content") or unit["title"])[:200],
	}
	return context
