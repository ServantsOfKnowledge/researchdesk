// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Site Page", {
	refresh(frm) {
		frm.set_intro(
			__(
				"A page of your own on the portal, at <b>/p/</b> followed by its address: about the organisation, a programme, how to take part. Tick <b>Published</b> to show it to visitors."
			),
			"blue"
		);
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Page"), () => window.open("/p/" + encodeURIComponent(frm.doc.slug), "_blank")).addClass("btn-primary");
		}
	},
});
