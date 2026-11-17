// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Book Contents"] = {
	add_fields: ["status", "quality"],
	get_indicator(doc) {
		return [__(doc.status), { Draft: "orange", "Needs a Look": "red", Published: "green", Rejected: "gray" }[doc.status], `status,=,${doc.status}`];
	},
};
