// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Disclosure Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method, args, done) =>
			frappe.call({ method: "sok_resdesk.disclosure." + method, args: { name: frm.doc.name, ...args }, freeze: true }).then(() => {
				frm.reload_doc();
				if (done) done();
			});
		if (frm.doc.status === "In review") {
			frm.add_custom_button(__("Decide"), () => frappe.confirm(__("Record the decision on every listed record?"), () => call("decide")));
		}
		if (frm.doc.status === "Decided") {
			frm.add_custom_button(__("Make the Package"), () => call("release"));
		}
		if (["In review", "Decided", "Received", "Released"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Close"), () =>
				frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Reason") }, (v) => call("close", { reason: v.reason }), __("Close this request"))
			);
		}
		if (frm.doc.records && frm.doc.records.length) {
			frm.add_custom_button(__("Preview a Page"), () =>
				frappe.prompt(
					[
						{ fieldname: "item", fieldtype: "Select", label: __("Record"), options: frm.doc.records.map((r) => r.item), reqd: 1 },
						{ fieldname: "leaf", fieldtype: "Int", label: __("Page"), default: 1, reqd: 1 },
					],
					(v) =>
						frappe.call({ method: "sok_resdesk.disclosure.preview", args: { name: frm.doc.name, item: v.item, leaf: v.leaf }, freeze: true }).then((r) => {
							const d = new frappe.ui.Dialog({ title: __("As it would be released"), size: "large" });
							d.$body.html($("<img>", { src: r.message, alt: __("The page with the covered parts black"), style: "max-width:100%" }));
							d.show();
						}),
					__("Preview a page")
				)
			);
		}
		if (frm.doc.release_error) frm.dashboard.set_headline(frappe.utils.escape_html(__("The package could not be made: {0}", [frm.doc.release_error])), "red");
		else if (frm.doc.status === "Preparing") frm.dashboard.set_headline(__("The package is being made. Reload in a few minutes."), "blue");
	},
});
