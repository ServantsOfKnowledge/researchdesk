import json

import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import base_url, settings
from sok_resdesk.portal import collection_cards, facet_labels

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	name = frappe.form_dict.get("collection")
	doc = (
		frappe.db.get_value(
			"RD Collection",
			name,
			["name", "title", "description", "cover_image", "curator", "published"],
			as_dict=True,
		)
		if name
		else None
	)
	viewer = access.viewer()
	if not doc or (not doc.published and not viewer["staff"]):
		raise frappe.PageDoesNotExistError
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.portal_title = s.portal_title or "SoK Research Desk"
	context.collection = doc
	context.count = next((c.count for c in collection_cards() if c.name == doc.name), 0)
	context.curator_name = frappe.db.get_value("User", doc.curator, "full_name") if doc.curator else ""
	context.title = f"{doc.title} · {context.portal_title}"
	context.viewer = viewer
	context.login_url = access.login_url(f"/library/collection/{doc.name}")
	context.visibilities = access.VISIBILITIES
	context.fixed_filters = json.dumps({"curated": [doc.name]})
	context.facet_labels = facet_labels()
	context.portal_url = f"{base_url()}/library/collection/{doc.name}"
	context.metatags = {
		"title": doc.title,
		"description": frappe.utils.strip_html(doc.description or "")[:300],
		"image": doc.cover_image or s.portal_logo or "",
	}
	return context
