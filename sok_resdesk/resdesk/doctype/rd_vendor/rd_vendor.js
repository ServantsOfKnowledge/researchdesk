// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Vendor", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Claim Letter"), () => {
			frappe.call({ method: "sok_resdesk.claims.letter", args: { vendor: frm.doc.name } }).then((r) => {
				const m = r.message || {};
				if (!m.text) return frappe.msgprint(__("This vendor owes nothing that is due for a claim."));
				const d = new frappe.ui.Dialog({
					title: __("Claim letter: {0} orders, {1} issues", [m.orders, m.issues]),
					fields: [
						{ fieldname: "text", fieldtype: "Small Text", label: __("Letter"), default: m.text, read_only: 0 },
						{ fieldtype: "HTML", options: `<p class="text-muted">${__("Copy it into your email or print it, then record that it was sent.")}</p>` },
					],
					primary_action_label: __("I Sent It"),
					primary_action() {
						frappe.call({ method: "sok_resdesk.claims.mark_claimed", args: { vendor: frm.doc.name }, freeze: true }).then(() => { d.hide(); frappe.show_alert({ message: __("Noted. These will not be claimed again for two weeks."), indicator: "green" }); });
					},
					secondary_action_label: __("Copy"),
					secondary_action() { frappe.utils.copy_to_clipboard(d.get_value("text")); },
				});
				d.show();
			});
		});
	},
});
