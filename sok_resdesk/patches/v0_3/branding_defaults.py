"""v0.3: switch on the new logo options for sites created before they existed."""

import frappe


def execute():
	frappe.reload_doc("resdesk", "doctype", "rd_settings")
	for field in ("logo_on_home", "show_title_in_navbar"):
		if not frappe.db.get_single_value("RD Settings", field):
			frappe.db.set_single_value("RD Settings", field, 1)
