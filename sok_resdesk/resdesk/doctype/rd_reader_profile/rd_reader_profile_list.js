frappe.listview_settings["RD Reader Profile"] = {
	add_fields: ["wants_reviewer", "wants_proofreader", "access_need"],
	get_indicator(doc) {
		if (doc.wants_reviewer || doc.wants_proofreader) return [__("Volunteer"), "green", "wants_reviewer,=,1"];
		return [__("Profile"), "gray"];
	},
};
