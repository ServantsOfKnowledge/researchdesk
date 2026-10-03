// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// A reader's note: open it on its page, and approve or reject a public one.

frappe.ui.form.on("RD Annotation", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_web_link(`/library/item/${encodeURIComponent(frm.doc.item)}?page=${frm.doc.leaf || 0}&view=text`, __("Open on its Page"));
		if (frm.doc.visibility === "Public" && frm.doc.review_status !== "Approved") {
			frm.add_custom_button(__("Approve"), () => review(frm, "Approved"), __("Review"));
		}
		if (frm.doc.visibility === "Public" && frm.doc.review_status !== "Rejected") {
			frm.add_custom_button(__("Reject"), () => review(frm, "Rejected"), __("Review"));
		}
		if (frm.doc.kind === "OCR error") {
			frm.set_intro(__("A reader reported an error in the page text: correct it when the book is proofread."), "orange");
		}
	},
});

function review(frm, decision) {
	frappe.call({ method: "sok_resdesk.annotations.review", args: { name: frm.doc.name, decision }, freeze: true }).then(() => frm.reload_doc());
}
