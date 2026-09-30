// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Collection", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.set_intro(
				__("A collection groups books under a title with its own page on the portal. Add books with rules below, from the Items list (Actions → Add to Collection) or from a portal search."),
				"blue"
			);
			return;
		}
		frm.add_web_link(`/library/collection/${encodeURIComponent(frm.doc.name)}`, __("Open on Portal"));
		frm.add_custom_button(__("Books in this Collection"), () => {
			frappe.route_options = { curated_collections: frm.doc.name };
			frappe.set_route("List", "RD Item");
		});
		if ((frm.doc.rules || []).length) {
			frm.add_custom_button(__("Apply Rules"), () =>
				frappe.call({
					method: "sok_resdesk.curation.apply_rules",
					args: { collection: frm.doc.name },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
						frm.reload_doc();
					},
				})
			);
		}
		frm.add_custom_button(__("Export Metadata"), () => frappe.new_doc("RD Export", { scope: "Collection", collection: frm.doc.name }));
	},
	title(frm) {
		if (frm.is_new() && frm.doc.title && !frm.doc.slug) {
			// preview only; the server makes the final web address
			frm.set_value(
				"slug",
				frm.doc.title
					.toLowerCase()
					.normalize("NFKC")
					.replace(/[^\p{L}\p{M}\p{N}\s_-]/gu, " ")
					.trim()
					.replace(/[\s_-]+/g, "-")
					.slice(0, 80)
			);
		}
	},
});
