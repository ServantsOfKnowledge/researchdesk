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
		// read the book's page images again with OCR, keeping only the pages that get better
		frm.add_custom_button(
			__("Re-OCR this book"),
			() =>
				frappe.call({ method: "sok_resdesk.reocr.engine_status" }).then((r) => {
					const st = r.message;
					if (!st.installed) return frappe.msgprint(__("The OCR engine (Tesseract) isn't installed on this server."));
					frappe.prompt(
						[
							{
								fieldname: "preset",
								fieldtype: "Select",
								label: __("Layout of the pages"),
								options: st.presets,
								default: "Whole page",
								description: __("Columns are read one by one, so they don't mix. Pages people have proofread are left alone; a page keeps its new text only if it reads better. For pages with their own layout, draw zones in Page & text → Proofread."),
							},
						],
						(v) =>
							frappe.call({ method: "sok_resdesk.reocr.enqueue_book", args: { item_id: frm.doc.name, preset: v.preset } }).then((x) => {
								frappe.show_alert({ message: x.message.message, indicator: "green" });
								frm.reload_doc();
							}),
						__("Re-OCR this book"),
						__("Start")
					);
				}),
			__("Actions")
		);
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
				__("Make Second Copy"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.second_copy_now",
						args: { item: frm.doc.name },
						freeze: true,
						freeze_message: __("Copying to the second place and checking it…"),
						callback: (r) => {
							frappe.show_alert({
								message: r.message.ok ? __("Second copy made: {0}", [r.message.where]) : __("The second copy failed its check"),
								indicator: r.message.ok ? "green" : "red",
							});
							frm.reload_doc();
						},
					}),
				__("Preservation")
			);
			frm.add_custom_button(
				__("Export BagIt"),
				() =>
					frappe.call({
						method: "sok_resdesk.preservation.export_book",
						args: { item: frm.doc.name },
						freeze: true,
						freeze_message: __("Making the bag…"),
						callback: (r) => {
							window.open(`/api/method/sok_resdesk.preservation.download_export?file=${encodeURIComponent(r.message.file)}`);
						},
					}),
				__("Preservation")
			);
			const serving = frm.doc.served_from_copy;
			frm.add_custom_button(
				serving ? __("Stop Serving From Our Copy") : __("Serve From Our Copy"),
				() =>
					frappe.confirm(
						serving
							? __("Stop serving this book's PDF from our copy? If archive.org doesn't have it either, it leaves the portal.")
							: __("Serve this book's PDF from our preservation copy, instead of archive.org's? Do this only when the library may share it: archive.org often darkens books for rights reasons."),
						() =>
							frappe
								.call({ method: "sok_resdesk.preservation.serve_from_copy", args: { item: frm.doc.name, on: serving ? 0 : 1 } })
								.then(() => frm.reload_doc())
					),
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
