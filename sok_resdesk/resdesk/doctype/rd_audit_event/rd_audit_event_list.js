frappe.listview_settings["RD Audit Event"] = {
	onload(list) {
		list.page.add_inner_button(__("Check the log"), () =>
			frappe.call({
				method: "sok_resdesk.audit.verify",
				callback: (r) =>
					frappe.msgprint({
						title: __("Audit log"),
						message: r.message.message,
						indicator: r.message.ok ? "green" : "red",
					}),
			})
		);
	},
};
