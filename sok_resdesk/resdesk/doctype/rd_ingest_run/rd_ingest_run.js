// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Ingest Run", {
	refresh(frm) {
		const running = ["Queued", "Running"].includes(frm.doc.status);
		if (running) {
			const pct = frm.doc.total_found ? Math.round((frm.doc.processed / frm.doc.total_found) * 100) : 0;
			frm.dashboard.show_progress(
				__("Ingest"),
				pct,
				`${frm.doc.processed} / ${frm.doc.total_found || "?"}` +
					(frm.doc.chunks_total ? ` · ${__("batches left")}: ${frm.doc.pending_chunks}/${frm.doc.chunks_total}` : "")
			);
			// Poll while the background job runs.
			clearTimeout(frm._rd_timer);
			frm._rd_timer = setTimeout(() => frm.reload_doc(), 4000);
		}
		if (running && frappe.user.has_role(["System Manager", "ResDesk Manager"])) {
			const stop = (force) =>
				frappe.call({
					method: "sok_resdesk.jobs.stop_run",
					args: { run: frm.doc.name, force },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
						frm.reload_doc();
					},
				});
			frm.add_custom_button(__("Stop"), () =>
				frappe.confirm(__("Stop this run? Running batches finish the book they are on, then stop. Books already ingested stay in the catalogue."), () => stop(0))
			, __("Stop"));
			frm.add_custom_button(__("Stop Now"), () =>
				frappe.confirm(__("Stop this run immediately? The book being processed is rolled back and picked up next time."), () => stop(1))
			, __("Stop"));
		}
		frm.add_custom_button(__("Background Jobs"), () => frappe.set_route("resdesk-jobs"));
		if (!frm.is_new()) {
			frm.add_custom_button(__("Items from this Profile"), () =>
				frappe.set_route("List", "RD Item", { ingest_profile: frm.doc.profile })
			);
		}
	},
});
