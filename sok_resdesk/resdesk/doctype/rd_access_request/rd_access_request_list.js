// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Access Request"] = {
	add_fields: ["status", "valid_until"],
	get_indicator(doc) {
		const colour = { Pending: "orange", Approved: "green", Declined: "red", Withdrawn: "gray" }[doc.status];
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
	onload(listview) {
		const decide = (status) => {
			const names = listview.get_checked_items(true);
			if (!names.length) return frappe.msgprint(__("Tick the requests first."));
			frappe.call({
				method: "sok_resdesk.approval.decide",
				args: { names: JSON.stringify(names), status },
				freeze: true,
				callback: (r) => {
					frappe.show_alert({ message: (r.message || {}).message, indicator: "green" });
					listview.refresh();
				},
			});
		};
		listview.page.add_actions_menu_item(__("Approve"), () => decide("Approved"));
		listview.page.add_actions_menu_item(__("Decline"), () => decide("Declined"));
	},
};
