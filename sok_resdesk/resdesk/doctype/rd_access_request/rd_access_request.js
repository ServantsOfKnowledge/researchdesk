// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Access Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		const colour = { Pending: "orange", Approved: "green", Declined: "red", Withdrawn: "gray" }[frm.doc.status];
		frm.page.set_indicator(__(frm.doc.status), colour || "gray");
		const decide = (status) =>
			(frm.is_dirty() ? frm.save() : Promise.resolve()).then(() =>
				frappe.call({
					method: "sok_resdesk.approval.decide",
					args: { names: JSON.stringify([frm.doc.name]), status },
					freeze: true,
					callback: () => frm.reload_doc(),
				})
			);
		if (frm.doc.status !== "Approved") frm.add_custom_button(__("Approve"), () => decide("Approved")).addClass("btn-primary");
		if (frm.doc.status !== "Declined") frm.add_custom_button(__("Decline"), () => decide("Declined"));
		frm.add_custom_button(__("Open the Book"), () => frappe.set_route("Form", "RD Item", frm.doc.item), __("Links"));
	},
});
