// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Archival Unit", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Browse the Hierarchy"), () => frappe.set_route("Tree", "RD Archival Unit"));
		if (frm.doc.published) frm.add_web_link(`/library/archive/${encodeURIComponent(frm.doc.name)}`, __("See on the Portal"));
		if (["Fonds", "Sub-fonds", "Collection"].includes(frm.doc.level)) {
			frm.add_custom_button(__("Download EAD3 (XML)"), () => window.open(`/api/method/sok_resdesk.archival.ead?unit=${encodeURIComponent(frm.doc.name)}`), __("Actions"));
		}
		frm.add_custom_button(__("Add a Part"), () => frappe.new_doc("RD Archival Unit", { parent_unit: frm.doc.name }), __("Actions"));
	},
});
