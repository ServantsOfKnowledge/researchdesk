frappe.ui.form.on("RD Reader Profile", {
	refresh(frm) {
		if (frm.is_new()) return;
		[["ResDesk Proofreader", __("Make a proofreader")], ["ResDesk Cataloguer", __("Make a reviewer (cataloguer)")]].forEach(([role, label]) => {
			frm.add_custom_button(label, () =>
				frappe.call("sok_resdesk.profile.grant", { user: frm.doc.user, role }).then((r) => frappe.show_alert({ message: r.message.message, indicator: "green" }))
			, __("Volunteers"));
		});
	},
});
