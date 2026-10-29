// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Serial Subscription", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty() || frm.doc.status !== "Active") return;
		frm.add_custom_button(__("Generate Issues"), () => frappe.prompt({ fieldname: "count", fieldtype: "Int", label: __("How many issues"), default: 12 }, (v) => frappe.call({ method: "sok_resdesk.serials.generate", args: { subscription: frm.doc.name, count: v.count }, freeze: true }).then((r) => { frappe.show_alert({ message: r.message.message, indicator: "green" }); }), __("Generate Issues"), __("Make Them"))).addClass("btn-primary");
		frm.add_custom_button(__("Issues"), () => frappe.set_route("List", "RD Serial Issue", { subscription: frm.doc.name }));
	},
});
