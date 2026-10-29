// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Serial Issue", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const call = (method, args = {}) => frappe.call({ method: "sok_resdesk.serials." + method, args: { issue: frm.doc.name, ...args }, freeze: true }).then((r) => { if (r.message && r.message.barcode) frappe.show_alert({ message: __("Barcode {0}", [r.message.barcode]), indicator: "green" }); frm.reload_doc(); });
		if (frm.doc.status !== "Received") frm.add_custom_button(__("Check In"), () => call("receive")).addClass("btn-primary");
		if (["Expected", "Late"].includes(frm.doc.status)) frm.add_custom_button(__("Claimed from Vendor"), () => call("claim"), __("Actions"));
		if (!["Received", "Missing"].includes(frm.doc.status)) frm.add_custom_button(__("Mark Missing"), () => call("mark_missing"), __("Actions"));
	},
});
