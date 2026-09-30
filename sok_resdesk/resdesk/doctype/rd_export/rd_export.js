// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Export", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(__("Choose a format and which books, then Save: the file is made straight away (big exports run in the background and appear here when done)."), "blue");
			return;
		}
		if (frm.doc.status === "Done" && frm.doc.file_url) {
			frm.set_intro(__("Ready: {0} books.", [frm.doc.item_count]) + ` <a href="${frm.doc.file_url}" target="_blank"><b>${__("Download")}</b></a>`, "green");
			frm.add_custom_button(__("Download"), () => window.open(frm.doc.file_url)).addClass("btn-primary");
		}
		if (["Queued", "Running"].includes(frm.doc.status)) {
			frm.set_intro(__("Working… this page refreshes by itself."), "orange");
			setTimeout(() => frm.reload_doc(), 4000);
		}
		if (["Done", "Failed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Export Again"), () =>
				frappe.call({ method: "sok_resdesk.transfer.rerun_export", args: { name: frm.doc.name }, freeze: true, callback: () => frm.reload_doc() })
			);
		}
		if (frm.doc.export_format && frm.doc.export_format.startsWith("Spreadsheet")) {
			frm.add_custom_button(__("Import Edited Spreadsheet"), () => frappe.new_doc("RD Metadata Import"));
		}
	},
});
