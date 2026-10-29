// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD ILL Request", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		frappe.call({ method: "sok_resdesk.ill.steps", args: { request: frm.doc.name } }).then((r) => {
			(r.message || []).forEach((to, i) => {
				const refusal = ["Refused", "Cancelled"].includes(to);
				frm.add_custom_button(__(to), () => frappe.prompt({ fieldname: "note", fieldtype: "Small Text", label: __("Note (optional)") }, (v) => frappe.call({ method: "sok_resdesk.ill.advance", args: { request: frm.doc.name, to, note: v.note || "" }, freeze: true }).then(() => frm.reload_doc()), __("Move to {0}", [__(to)]), __("Move")), refusal ? __("Close Without Lending") : null).addClass(!refusal && i === 0 ? "btn-primary" : "");
			});
		});
		if (frm.doc.direction === "Borrowing" && frm.doc.fee > 0 && !frm.doc.fee_charged) frm.add_custom_button(__("Charge the Fee to the Member"), () => frappe.call({ method: "sok_resdesk.ill.charge_fee", args: { request: frm.doc.name }, freeze: true }).then(() => frm.reload_doc()), __("Actions"));
	},
});
