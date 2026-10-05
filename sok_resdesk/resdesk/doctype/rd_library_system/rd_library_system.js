// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// A library system's catalogue matched to the books here, and the links sent back (librarysystems.py)
frappe.ui.form.on("RD Library System", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Bring in the library system's catalogue (a MARC export, or its OAI-PMH server), see which of its records are books here, and send the links to the digital copies back into it. <b>Import Now</b> reads the records and matches them; unsure matches wait under <b>Records to Review</b>."
			),
			"blue"
		);
		if (frm.is_new()) return;
		const run = (action, message) =>
			frappe.call({
				method: "sok_resdesk.librarysystems.start",
				args: { system: frm.doc.name, action },
				callback: () => {
					frappe.show_alert({ message, indicator: "green" });
					frm.reload_doc();
				},
			});
		frm.add_custom_button(__("Import Now"), () => run("import", __("Importing in the background"))).addClass("btn-primary");
		frm.add_custom_button(__("Match Again"), () => run("match", __("Matching in the background")), __("Actions"));
		frm.add_custom_button(
			__("Records to Review"),
			() => frappe.set_route("List", "RD Library Record", { library_system: frm.doc.name, status: "To Review" }),
			__("Actions")
		);
		frm.add_custom_button(
			__("All Records"),
			() => frappe.set_route("List", "RD Library Record", { library_system: frm.doc.name }),
			__("Actions")
		);
		if (frm.doc.push_target) {
			frm.add_custom_button(
				__("Send Links Back"),
				() =>
					frappe.confirm(
						__("Add links to the books here to every linked record in {0} that doesn't have them yet? Nothing else in its records changes.", [frappe.utils.escape_html(frm.doc.system_name)]),
						() => run("send", __("Sending links in the background"))
					),
				__("Actions")
			);
		}
		frm.add_custom_button(
			__("Download Records With Links"),
			() =>
				window.open(
					`/api/method/sok_resdesk.librarysystems.download_with_links?system=${encodeURIComponent(frm.doc.name)}`
				),
			__("Actions")
		);
	},
});
