// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

const COLOURS = { Draft: "orange", "Needs a Look": "red", Published: "green", Rejected: "gray" };

frappe.ui.form.on("RD Book Contents", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.status;
		frm.page.set_indicator(__(status), COLOURS[status] || "gray");
		if (status === "Published") {
			frm.add_custom_button(__("Withdraw"), () => set_status(frm, "Draft"));
			frm.add_web_link(`/library/item/${encodeURIComponent(frm.doc.item)}`, __("View on Portal"));
		} else {
			frm.add_custom_button(__("Publish"), () => set_status(frm, "Published")).addClass("btn-primary");
			if (status !== "Rejected") frm.add_custom_button(__("Reject"), () => set_status(frm, "Rejected"));
			frm.add_custom_button(__("Read Again"), () => read_again(frm, 0), __("Actions"));
			frm.add_custom_button(__("Read the Contents Pages Again (OCR)"), () => read_again(frm, 1), __("Actions"));
		}
		frm.add_custom_button(__("Open the Book"), () => frappe.set_route("Form", "RD Item", frm.doc.item), __("Links"));
	},
});

function set_status(frm, status) {
	(frm.is_dirty() ? frm.save() : Promise.resolve()).then(() =>
		frappe.call({
			method: "sok_resdesk.contents.set_status",
			args: { item_id: frm.doc.name, status },
			freeze: true,
			callback: () => frm.reload_doc(),
		})
	);
}

function read_again(frm, reread) {
	frappe.confirm(__("This replaces the headings below with a new reading. Continue?"), () =>
		frappe.call({
			method: "sok_resdesk.contents.extract",
			args: { item_id: frm.doc.item, reread },
			freeze: true,
			callback: (r) => {
				frappe.show_alert({ message: (r.message || {}).message, indicator: "green" }, 7);
				frm.reload_doc();
			},
		})
	);
}
