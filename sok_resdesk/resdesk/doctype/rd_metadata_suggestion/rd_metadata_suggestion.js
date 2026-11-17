// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

const COLOURS = { Draft: "orange", Applied: "green", Rejected: "gray" };

frappe.ui.form.on("RD Metadata Suggestion", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		frm.page.set_indicator(__(status), COLOURS[status] || "gray");
		if (status === "Draft") {
			frm.add_custom_button(__("Apply to the Book"), () => decide(frm, "Applied")).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => decide(frm, "Rejected"));
			frm.add_custom_button(__("Read Again"), () => read_again(frm), __("Actions"));
		}
		frm.add_custom_button(__("Open the Book"), () => frappe.set_route("Form", "RD Item", frm.doc.item), __("Links"));
	},
});

function decide(frm, status) {
	(frm.is_dirty() ? frm.save() : Promise.resolve()).then(() =>
		frappe.call({
			method: "sok_resdesk.frontmatter.decide",
			args: { item_id: frm.doc.name, status },
			freeze: true,
			callback: () => frm.reload_doc(),
		})
	);
}

function read_again(frm) {
	frappe.confirm(__("This replaces the details below with a new reading. Continue?"), () =>
		frappe.call({
			method: "sok_resdesk.frontmatter.extract",
			args: { item_id: frm.doc.item },
			freeze: true,
			callback: (r) => {
				frappe.show_alert({ message: (r.message || {}).message, indicator: "green" }, 7);
				frm.reload_doc();
			},
		})
	);
}
