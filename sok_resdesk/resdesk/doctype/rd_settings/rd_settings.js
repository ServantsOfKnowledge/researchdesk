// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Search Engine"), () =>
			frappe.call({
				method: "sok_resdesk.search.setup_indexes",
				freeze: true,
				freeze_message: __("Connecting to Meilisearch…"),
				callback: (r) => {
					frappe.msgprint({ title: __("Search engine"), message: r.message, indicator: "green" });
					frm.reload_doc();
				},
			})
		);
		frm.add_custom_button(__("Rebuild Search Index"), () =>
			frappe.confirm(
				__("Re-index every catalogue record? Page text is fetched again from the Internet Archive, so this can take a while for large catalogues."),
				() =>
					frappe.call({
						method: "sok_resdesk.search.enqueue_rebuild",
						callback: () =>
							frappe.show_alert({ message: __("Rebuild queued"), indicator: "green" }),
					})
			)
		);
		frm.add_web_link("/library", __("Open Portal"));
	},
});
