// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Ingest Run", {
	refresh(frm) {
		const running = ["Queued", "Running"].includes(frm.doc.status);
		if (running) {
			const pct = frm.doc.total_found ? Math.round((frm.doc.processed / frm.doc.total_found) * 100) : 0;
			frm.dashboard.show_progress(__("Ingest"), pct, `${frm.doc.processed} / ${frm.doc.total_found || "?"}`);
			// Poll while the background job runs.
			clearTimeout(frm._rd_timer);
			frm._rd_timer = setTimeout(() => frm.reload_doc(), 4000);
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Items from this Profile"), () =>
				frappe.set_route("List", "RD Item", { ingest_profile: frm.doc.profile })
			);
		}
	},
});
