// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Patron", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Print ID Card"), () => window.open("/library/card?patron=" + encodeURIComponent(frm.doc.name), "_blank"));
		frm.add_custom_button(__("Circulation Desk"), () => frappe.set_route("resdesk-circulation"));
		if (frm.doc.status === "Pending") {
			const act = (method, ask) => () => frappe.confirm(ask, () => frappe.call({ method: "sok_resdesk.patrons." + method, args: { patron: frm.doc.name }, freeze: true }).then(() => frm.reload_doc()));
			frm.add_custom_button(__("Approve"), act("approve", __("Make {0} a member?", [frm.doc.full_name])), __("Sign-up"));
			frm.add_custom_button(__("Turn Down"), act("reject", __("Turn down {0}?", [frm.doc.full_name])), __("Sign-up"));
			frm.set_intro(__("This person joined the portal and the roster could not confirm them. Look at the ID card photo, then approve or turn down."), "orange");
		}
	},
});
