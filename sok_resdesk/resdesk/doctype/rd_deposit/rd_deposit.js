// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// A deposit in the Desk: staff review it here (accept, ask for changes, reject); the person who
// deposited usually works on the portal (/library/deposit).
frappe.ui.form.on("RD Deposit", {
	refresh(frm) {
		if (frm.is_new()) return;
		const colour = { Draft: "gray", Submitted: "orange", "Needs Changes": "yellow", Accepted: "green", Rejected: "red", Withdrawn: "gray" }[frm.doc.status];
		frm.dashboard.set_headline_alert(__(frm.doc.status), colour);
		if (frm.doc.warnings) frm.set_intro(frappe.utils.escape_html(frm.doc.warnings).replace(/\n/g, "<br>"), "orange");
		if (frm.doc.item) frm.add_web_link(`/library/item/${encodeURIComponent(frm.doc.item)}`, __("View on Portal"));
		if (frm.doc.status !== "Submitted") return;
		const call = (method, args) =>
			frappe.call({ method: `sok_resdesk.deposit.${method}`, args: { name: frm.doc.name, ...args }, freeze: true }).then(() => frm.reload_doc());
		frm.add_custom_button(__("Accept"), () =>
			frappe.prompt(
				[
					{ fieldname: "collection", fieldtype: "Link", options: "RD Collection", label: __("List in Collection"), default: frm.doc.collection },
					{ fieldname: "notes", fieldtype: "Small Text", label: __("Note to the Depositor (optional)") },
				],
				(v) => call("accept", v),
				__("Accept this deposit"),
				__("Accept")
			)
		, __("Review")).addClass("btn-primary");
		const ask = (method, title) => () =>
			frappe.prompt([{ fieldname: "notes", fieldtype: "Small Text", label: __("Note to the Depositor"), reqd: 1 }], (v) => call(method, v), title, __("Send"));
		frm.add_custom_button(__("Ask for Changes"), ask("request_changes", __("What needs to change?")), __("Review"));
		frm.add_custom_button(__("Reject"), ask("reject", __("Why is it not accepted?")), __("Review"));
	},
});
