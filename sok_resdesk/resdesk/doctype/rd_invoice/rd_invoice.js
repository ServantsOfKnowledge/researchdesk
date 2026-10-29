// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Invoice", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const act = (method, ask, args = {}) => () => frappe.confirm(ask, () => frappe.call({ method: "sok_resdesk.acquisitions." + method, args: { invoice: frm.doc.name, ...args }, freeze: true }).then(() => frm.reload_doc()));
		if (frm.doc.match && frm.doc.match !== "ok") frm.set_intro(__("This invoice does not agree with the order: {0}. Check before approving.", [frm.doc.match]), "orange");
		if (frm.doc.status === "Draft") frm.add_custom_button(__("Approve"), act("invoice_approve", __("Approve this invoice for payment?"))).addClass("btn-primary");
		if (frm.doc.status === "Approved") frm.add_custom_button(__("Record Payment"), () => frappe.prompt({ fieldname: "note", fieldtype: "Data", label: __("Cheque, transfer or voucher number") }, (v) => frappe.call({ method: "sok_resdesk.acquisitions.invoice_pay", args: { invoice: frm.doc.name, note: v.note || "" }, freeze: true }).then(() => frm.reload_doc()), __("Record Payment"), __("Mark Paid"))).addClass("btn-primary");
		if (["Draft", "Approved"].includes(frm.doc.status)) frm.add_custom_button(__("Cancel Invoice"), act("invoice_cancel", __("Cancel this invoice?")), __("Actions"));
	},
});
