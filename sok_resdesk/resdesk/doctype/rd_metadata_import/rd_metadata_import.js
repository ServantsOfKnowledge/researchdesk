// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Metadata Import", {
	refresh(frm) {
		frm.set_intro(
			__("Edit many books at once: export a Spreadsheet (CSV or Excel), change it, attach it here, Preview, then Apply. Books you change keep your edits when they are re-ingested."),
			"blue"
		);
		if (frm.is_new()) return;
		const call = (method, label) =>
			frappe.call({
				method: `sok_resdesk.transfer.${method}`,
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: label,
				callback: (r) => {
					frappe.show_alert({ message: r.message.message, indicator: "green" }, 8);
					frm.reload_doc();
				},
			});
		if (frm.doc.import_file && !["Queued", "Applying"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Preview Changes"), () => call("preview_import", __("Reading the spreadsheet…")));
		}
		if (frm.doc.status === "Previewed" && frm.doc.changed) {
			frm.add_custom_button(__("Apply Changes"), () =>
				frappe.confirm(__("Change {0} books now?", [frm.doc.changed]), () => call("apply_import", __("Updating books…")))
			).addClass("btn-primary");
		}
		if (["Queued", "Applying"].includes(frm.doc.status)) setTimeout(() => frm.reload_doc(), 4000);
		frm.add_custom_button(__("Get a Spreadsheet to Edit"), () => frappe.new_doc("RD Export", { export_format: "Spreadsheet (Excel)" }));
	},
});
