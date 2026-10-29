// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Copy", {
	refresh(frm) {
		if (!frm.is_new()) frm.add_custom_button(__("Print Barcode Label"), () => window.open("/library/labels?codes=" + encodeURIComponent(frm.doc.name), "_blank"));
	},
});
