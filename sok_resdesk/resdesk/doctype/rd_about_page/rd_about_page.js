// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD About Page", {
	refresh(frm) {
		frm.set_intro(
			__(
				"The introduction to your library at <b>/about</b>: what it is and how to use it, with a button to the library. Fill in the parts you want; empty parts are left out. Save, then <b>View Page</b>."
			),
			"blue"
		);
		frm.add_custom_button(__("View Page"), () => window.open("/about", "_blank")).addClass("btn-primary");
		frm.add_custom_button(__("Open the Library"), () => window.open("/library", "_blank"));
	},
});
