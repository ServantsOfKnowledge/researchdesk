// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// One library record and the books here it may be: choose one, or none
frappe.ui.form.on("RD Library Record", {
	refresh(frm) {
		const esc = frappe.utils.escape_html;
		let cands = [];
		try {
			cands = JSON.parse(frm.doc.candidates || "[]");
		} catch (e) {
			cands = [];
		}
		const rows = cands
			.map(
				(c) => `<tr><td><a href="/app/rd-item/${encodeURIComponent(c.item_id)}">${esc(c.title || c.item_id)}</a><br><span class="text-muted small">${esc(c.item_id)}</span></td>
				<td>${(c.score * 100).toFixed(0)}%</td><td class="small">${esc(c.why || "")}</td>
				<td><button class="btn btn-xs btn-default" data-item="${esc(c.item_id)}">${__("This is the book")}</button></td></tr>`
			)
			.join("");
		frm.get_field("candidates_html").$wrapper.html(
			cands.length
				? `<table class="table table-bordered small"><thead><tr><th>${__("Book here")}</th><th>${__("Score")}</th><th>${__("Matched by")}</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
				: `<p class="text-muted">${__("No book here looks like this record.")}</p>`
		);
		frm.get_field("candidates_html").$wrapper.find("button[data-item]").on("click", (e) =>
			frappe.call({
				method: "sok_resdesk.librarysystems.decide",
				args: { record: frm.doc.name, item: e.currentTarget.dataset.item },
				callback: () => frm.reload_doc(),
			})
		);
		if (frm.doc.status !== "Not This Book") {
			frm.add_custom_button(__("Not a Match"), () =>
				frappe.call({
					method: "sok_resdesk.librarysystems.decide",
					args: { record: frm.doc.name, not_a_match: 1 },
					callback: () => frm.reload_doc(),
				})
			);
		}
	},
});
