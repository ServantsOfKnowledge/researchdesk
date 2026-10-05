// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Export", {
	refresh(frm) {
		if (frm.is_new() && frm.doc.export_format === "Calibre library (zip)") {
			frm.add_custom_button(__("Estimate Size"), () =>
				frappe.call({ method: "sok_resdesk.calibre_export.estimate", args: { values: frm.doc }, freeze: true, freeze_message: __("Counting the files…") }).then((r) => {
					const e = r.message;
					frappe.msgprint({
						title: __("Calibre library"),
						message:
							__("{0} books chosen: {1} have files held here ({2} files, about {3} MB); {4} are listed in not-included.csv with a link to where they are.", [e.books, e.with_files, e.files, e.megabytes, e.not_included]) +
							(e.problem ? `<p class="text-danger">${frappe.utils.escape_html(e.problem)}</p>` : ""),
					});
				})
			);
		}
		if (frm.is_new() && frm.doc.export_format === "Offline copy (zip, for Kiwix)") {
			frm.add_custom_button(__("Estimate Size"), () =>
				frappe.call({ method: "sok_resdesk.offline_export.estimate", args: { values: frm.doc }, freeze: true, freeze_message: __("Counting…") }).then((r) => {
					const e = r.message;
					frappe.msgprint({
						title: __("Offline copy"),
						message:
							__("{0} books chosen: {1} with files, {2} with their text, {3} with details only; about {4} MB.", [e.books, e.with_files, e.with_text, e.details_only, e.megabytes]) +
							" " + (e.zim ? __("A ZIM file will be made too.") : __("This server cannot make a ZIM file itself (zimwriterfs): the zip says how.")) +
							(e.problem ? `<p class="text-danger">${frappe.utils.escape_html(e.problem)}</p>` : ""),
					});
				})
			);
		}
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
