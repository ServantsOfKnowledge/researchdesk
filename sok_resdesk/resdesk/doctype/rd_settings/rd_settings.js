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
		frm.add_custom_button(__("Apply Access Rules"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Apply access rules to books already in the catalogue"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p>${__("Each book gets the visibility its ingest profile, the first matching rule or the default gives it. New books get this automatically; this updates the ones already here.")}</p>`,
					},
					{
						fieldname: "include_manual",
						fieldtype: "Check",
						label: __("Also change books whose visibility was set by hand or in bulk"),
					},
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "sok_resdesk.access.apply_rules",
						args: { include_manual: values.include_manual ? 1 : 0 },
						callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }),
					});
				},
			});
			frm.is_dirty() ? frappe.msgprint(__("Save the settings first.")) : d.show();
		});
		frm.add_custom_button(__("Background Jobs"), () => frappe.set_route("resdesk-jobs"));
		if (frm.doc.preservation_root) {
			frm.add_custom_button(
				__("Make Every Second Copy Now"),
				() =>
					frappe.call("sok_resdesk.preservation.enqueue_second_copies").then((r) =>
						frappe.show_alert({ message: __("{0} books queued for their second copy", [r.message]), indicator: "green" })
					),
				__("Preservation")
			);
			frm.add_custom_button(
				__("BagIt Exports"),
				() =>
					frappe.call("sok_resdesk.preservation.exports").then((r) => {
						const rows = r.message || [];
						const esc = frappe.utils.escape_html;
						frappe.msgprint({
							title: __("BagIt Exports"),
							message: rows.length
								? `<p class="text-muted">${__("Kept for two weeks; make them again from a book or a collection.")}</p><ul>${rows
										.map(
											(x) =>
												`<li><a href="/api/method/sok_resdesk.preservation.download_export?file=${encodeURIComponent(x.file)}">${esc(x.file)}</a> · ${frappe.form.formatters.Float(x.bytes / 1048576, { precision: 1 })} MB · ${esc(x.made)}</li>`
										)
										.join("")}</ul>`
								: __("No exports yet: Export BagIt on a book or a collection makes one."),
						});
					}),
				__("Preservation")
			);
		}
		frm.add_custom_button(__("Reader Requests"), () => frappe.set_route("List", "RD Reader Request", { status: "Pending" }));
		frm.add_web_link("/", __("Open Portal"));
	},
});
