frappe.ui.form.on("RD Push Run", {
	refresh(frm) {
		clearTimeout(frm._rd_timer);
		const active = ["Queued", "Running"].includes(frm.doc.status);
		if (active) {
			frm.add_custom_button(__("Cancel"), () =>
				frappe.call({ method: "sok_resdesk.outbound.cancel", args: { run_name: frm.doc.name } }).then(() => frm.reload_doc())
			);
			frm._rd_timer = setTimeout(() => {
				if (frappe.get_route_str() === `Form/RD Push Run/${frm.doc.name}`) frm.reload_doc();
			}, 4000);
		}
		frm.add_custom_button(__("Push Target"), () => frappe.set_route("Form", "RD Push Target", frm.doc.target));
	},
});
