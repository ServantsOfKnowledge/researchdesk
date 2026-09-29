// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Item", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_web_link(`/library/item/${encodeURIComponent(frm.doc.item_id)}`, __("View on Portal"));
		if (frm.doc.source_url) {
			frm.add_custom_button(__("Open Source"), () => window.open(frm.doc.source_url), __("Links"));
		}
		frm.add_custom_button(
			__("Refresh from Source"),
			() =>
				frappe.call({
					method: "sok_resdesk.ingest.refresh_item",
					args: { item_id: frm.doc.item_id },
					freeze: true,
					freeze_message: __("Fetching from the Internet Archive…"),
					callback: () => frm.reload_doc(),
				}),
			__("Actions")
		);
		frm.add_custom_button(
			__("Re-index"),
			() =>
				frappe.call({
					method: "sok_resdesk.search.reindex_item",
					args: { item_id: frm.doc.item_id },
					freeze: true,
					callback: () => {
						frappe.show_alert({ message: __("Re-indexed"), indicator: "green" });
						frm.reload_doc();
					},
				}),
			__("Actions")
		);
		if (frm.doc.thumbnail_url) {
			frm.set_intro(
				`<img src="${frm.doc.thumbnail_url}" style="max-height:120px;border-radius:4px;margin-right:12px;float:left">
				 <div>${frappe.utils.escape_html(frm.doc.creator_display || "")}<br>${frm.doc.year || ""} · ${
					frm.doc.language_label || ""
				} · ${frm.doc.page_count || "?"} ${__("pages")}</div><div style="clear:both"></div>`,
				"blue"
			);
		}
	},
});
