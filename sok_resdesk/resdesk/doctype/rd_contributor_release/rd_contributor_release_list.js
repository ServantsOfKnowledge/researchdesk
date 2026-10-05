// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// One release per person, and it is theirs: the list goes straight to it.
frappe.listview_settings["RD Contributor Release"] = {
	onload() {
		frappe.db.exists("RD Contributor Release", frappe.session.user).then((found) => {
			if (found) return frappe.set_route("Form", "RD Contributor Release", frappe.session.user);
			frappe.new_doc("RD Contributor Release", { user: frappe.session.user, licence: "CC-BY-4.0" });
		});
	},
};
