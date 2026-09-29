// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Ingest Profile", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Choose a collection, a search, or a list of identifiers from archive.org. Use <b>Check Count</b> to see how many items match, then <b>Run Ingest</b>. Start with a small Maximum Items value for a test."
			),
			"blue"
		);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Check Count"), () => {
			frappe.call({
				method: "sok_resdesk.ingest.count_profile",
				args: { profile: frm.doc.name },
				freeze: true,
				freeze_message: __("Asking the Internet Archive…"),
				callback: (r) => {
					frappe.msgprint({
						title: __("Matching items"),
						message: __("{0} items match this profile on the Internet Archive.", [
							(r.message.count || 0).toLocaleString(),
						]) + `<br><br><code>${frappe.utils.escape_html(r.message.query)}</code>`,
						indicator: "blue",
					});
					frm.reload_doc();
				},
			});
		});

		frm.add_custom_button(__("Run Ingest"), () => {
			const limit = frm.doc.max_items ? frm.doc.max_items : __("all");
			frappe.confirm(__("Start ingesting up to {0} items in the background?", [limit]), () => {
				frappe.call({
					method: "sok_resdesk.ingest.start_ingest",
					args: { profile: frm.doc.name },
					callback: (r) => {
						frappe.show_alert({ message: __("Ingest queued: {0}", [r.message]), indicator: "green" });
						frappe.set_route("Form", "RD Ingest Run", r.message);
					},
				});
			});
		}).addClass("btn-primary");

		frm.add_custom_button(__("Items from this Profile"), () =>
			frappe.set_route("List", "RD Item", { ingest_profile: frm.doc.name })
		);
		frm.add_custom_button(__("Run History"), () =>
			frappe.set_route("List", "RD Ingest Run", { profile: frm.doc.name })
		);
	},
});
