import frappe
from frappe import _

from sok_resdesk import access, features
from sok_resdesk.core.barcode import svg
from sok_resdesk.lending import STAFF
from sok_resdesk.portal import library_url

no_cache = 1


def get_context(context):
	"""Barcode labels for copies, to print and stick on books (staff)."""
	if not features.on("lending"):
		frappe.local.flags.redirect_location = library_url()
		raise frappe.Redirect
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = access.login_url("/library/labels")
		raise frappe.Redirect
	if not set(frappe.get_roles()) & set(STAFF):
		raise frappe.PermissionError
	codes = [c.strip().upper() for c in (frappe.form_dict.get("codes") or "").split(",") if c.strip()][:500]
	labels = []
	for code in codes:
		row = frappe.db.get_value("RD Copy", code, ["name", "item_title", "call_number"], as_dict=True)
		if row:
			labels.append(
				{
					"code": row.name,
					"title": row.item_title or "",
					"call": row.call_number or "",
					"svg": svg(row.name, height=36, module=2),
				}
			)
	if not labels:
		raise frappe.PageDoesNotExistError
	context.update(
		{"no_cache": 1, "full_width": 1, "show_sidebar": 0, "labels": labels, "title": _("Barcode labels")}
	)
	return context
