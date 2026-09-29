// Reader Requests list: approve or reject several people at once.
frappe.listview_settings["RD Reader Request"] = {
	get_indicator(doc) {
		return {
			Pending: [__("Pending"), "orange", "status,=,Pending"],
			Approved: [__("Approved"), "green", "status,=,Approved"],
			Rejected: [__("Rejected"), "red", "status,=,Rejected"],
		}[doc.status];
	},
	onload(listview) {
		["Approved", "Rejected"].forEach((status) => {
			listview.page.add_actions_menu_item(status === "Approved" ? __("Approve") : __("Reject"), () => {
				const names = listview.get_checked_items(true);
				frappe.call({
					method: "sok_resdesk.access.decide_requests",
					args: { names, status },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({ message: r.message, indicator: "green" });
						listview.refresh();
					},
				});
			});
		});
	},
};
