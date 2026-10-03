import frappe

from sok_resdesk import access
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""Where a permanent ARK leads when its book is no longer on the portal: what it was, what
	happened to it and where to go instead. The ARK keeps working; it never ends in a 404."""
	access.require_login_for_portal()
	from sok_resdesk.identifiers import resolve

	ark = frappe.form_dict.get("ark") or ""
	if ark.lower().startswith("doi:"):  # a deleted book that had a DOI but no ARK (datacite.py)
		stone = frappe.db.get_value("RD Tombstone", {"ark": ark}, ["name", "item_id", "title"], as_dict=True)
		if not stone:
			raise frappe.PageDoesNotExistError
		where = {"kind": "tombstone", "ark": ark, "item": None, "tombstone": stone}
	else:
		where = resolve(ark)
	if where["kind"] == "unknown":
		raise frappe.PageDoesNotExistError
	if where["kind"] == "book":  # back on the portal since the link was made
		frappe.local.flags.redirect_location = f"/library/item/{where['item'].name}"
		raise frappe.Redirect
	s = settings()
	stone = frappe.get_doc("RD Tombstone", where["tombstone"].name) if where.get("tombstone") else None
	item = where.get("item")
	# a book that is only unpublished says no more than that; who may see what stays as it is
	context.update(
		{
			"no_cache": 1,
			"full_width": 1,
			"show_sidebar": 0,
			"portal_title": s.portal_title or "SOK Research Desk",
			"ark": where["ark"],
			"stone": stone,
			"hidden": bool(item and not stone),
			"replaced_by": stone.replaced_by if stone and stone.replaced_by else "",
		}
	)
	context.title = frappe._("No longer available") + f" · {context.portal_title}"
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
