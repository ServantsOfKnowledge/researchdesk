// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Archival Unit"] = {
	add_fields: ["level", "published"],
	onload(list) {
		list.page.add_inner_button(__("Hierarchy"), () => frappe.set_route("Tree", "RD Archival Unit"));
	},
};
