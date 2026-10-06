// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// There is one account record per person, and it is theirs: the list goes straight to it.
frappe.listview_settings["RD Archive Account"] = {
	onload() {
		frappe.db.exists("RD Archive Account", frappe.session.user).then((found) => {
			if (found) return frappe.set_route("Form", "RD Archive Account", frappe.session.user);
			frappe.new_doc("RD Archive Account", { user: frappe.session.user });
		});
	},
};
