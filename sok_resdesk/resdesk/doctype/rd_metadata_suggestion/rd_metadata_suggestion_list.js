// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Metadata Suggestion"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return [__(doc.status), { Draft: "orange", Applied: "green", Rejected: "gray" }[doc.status], `status,=,${doc.status}`];
	},
};
