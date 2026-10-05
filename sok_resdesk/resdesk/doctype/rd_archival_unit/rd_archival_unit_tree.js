// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.treeview_settings["RD Archival Unit"] = {
	filters: [],
	root_label: __("All archives"),
	title: __("Archival description"),
	fields: [
		{ fieldtype: "Data", fieldname: "ref_code", label: __("Reference Code"), reqd: 1 },
		{ fieldtype: "Data", fieldname: "title", label: __("Title"), reqd: 1 },
		{ fieldtype: "Select", fieldname: "level", label: __("Level"), options: ["Fonds", "Sub-fonds", "Collection", "Series", "Sub-series", "File", "Item"], reqd: 1 },
	],
	ignore_fields: ["parent_unit"],
	onrender(node) {
		if (node.data && node.data.level) node.$tree_link && node.$tree_link.attr("title", node.data.level);
	},
};
