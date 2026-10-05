// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// There is one account record per person, and it is theirs: the list goes straight to it.
frappe.listview_settings["RD Wikimedia Account"] = {
	onload() {
		frappe.db.exists("RD Wikimedia Account", frappe.session.user).then((found) => {
			if (found) return frappe.set_route("Form", "RD Wikimedia Account", frappe.session.user);
			frappe.new_doc("RD Wikimedia Account", { user: frappe.session.user });
		});
	},
};
