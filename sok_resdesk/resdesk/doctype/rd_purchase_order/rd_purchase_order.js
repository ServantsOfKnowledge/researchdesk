// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Purchase Order", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		const call = (method, args, then) => frappe.call({ method: "sok_resdesk.acquisitions." + method, args: { order: frm.doc.name, ...args }, freeze: true }).then((r) => then(r.message || {}));
		if (frm.doc.status === "Draft") {
			frm.add_custom_button(__("Place Order"), () => call("place", {}, () => frm.reload_doc())).addClass("btn-primary");
		}
		if (["Ordered", "Part Received"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Receive Books"), () => {
				const rows = frm.doc.lines.filter((l) => (l.quantity || 0) > (l.received || 0));
				const fields = rows.map((l) => ({ fieldname: "q" + l.idx, fieldtype: "Int", label: `${l.title} (${l.quantity - (l.received || 0)} ${__("outstanding")})`, default: l.quantity - (l.received || 0) }));
				fields.push({ fieldname: "location", fieldtype: "Data", label: __("Shelf or Branch") });
				frappe.prompt(fields, (v) => {
					const q = {};
					rows.forEach((l) => (q[l.idx] = v["q" + l.idx] || 0));
					call("receive", { quantities: JSON.stringify(q), location: v.location || "" }, (m) => {
						frappe.msgprint({ title: __("Books received"), message: __("{0} copies added.", [(m.copies || []).length]) + ` <a href="/app/rd-copy?order=${encodeURIComponent(frm.doc.name)}">${__("See the copies")}</a> · <a href="/library/labels?codes=${(m.copies || []).map((c) => encodeURIComponent(c.barcode)).join(",")}" target="_blank">${__("Print barcode labels")}</a>` });
						frm.reload_doc();
					});
				}, __("Receive Books"), __("Add to the Library"));
			}).addClass("btn-primary");
		}
		if (["Draft", "Ordered"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Cancel Order"), () => frappe.confirm(__("Cancel this order?"), () => call("cancel", {}, () => frm.reload_doc())), __("Actions"));
		}
	},
});
