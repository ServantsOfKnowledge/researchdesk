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
		if (frm.doc.persistent_id) {
			frm.add_web_link(`/${frm.doc.persistent_id}`, __("Permanent Link (ARK)"));
		}
		// the library's own copy (Settings → Preservation)
		frm.add_custom_button(
			__("Preserve Now"),
			() =>
				frappe.call({
					method: "sok_resdesk.preservation.preserve_now",
					args: { item: frm.doc.name },
					freeze: true,
					freeze_message: __("Copying the book's files and checking them…"),
					callback: (r) => {
						frappe.show_alert({
							message: r.message.changed ? __("Copied: version {0}", [r.message.version]) : __("The copy is up to date"),
							indicator: "green",
						});
						frm.reload_doc();
					},
				}),
			__("Preservation")
		);
		if (frm.doc.preserved_on) {
			frm.add_custom_button(
				__("Check Copy"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.check_now",
						args: { item: frm.doc.name },
						freeze: true,
						callback: (r) => {
							const ok = r.message.ok;
							frappe.show_alert({
								message: ok ? __("All {0} files match their checksums", [r.message.checked]) : r.message.problems.slice(0, 3).join("; "),
								indicator: ok ? "green" : "red",
							});
							frm.reload_doc();
						},
					}),
				__("Preservation")
			);
			frm.add_custom_button(
				__("History"),
				() => frappe.set_route("List", "RD Preservation Event", { item: frm.doc.name }),
				__("Preservation")
			);
		}
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
