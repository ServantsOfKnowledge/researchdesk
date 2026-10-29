// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("RD Budget", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call({ method: "sok_resdesk.acquisitions.budget_summary", args: { budget: frm.doc.name } }).then((r) => {
			const s = r.message || {};
			frm.set_intro(
				__("Budget {0}: committed by orders {1}, spent on invoices {2}, left {3}.", [s.amount, s.committed, s.spent, s.remaining]),
				s.remaining < 0 ? "red" : "blue"
			);
		});
	},
});
