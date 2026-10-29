// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Patron"] = {
	add_fields: ["status", "category"],
	get_indicator(doc) {
		const colour = { Active: "green", Pending: "orange", Listed: "gray", Expired: "red", Blocked: "red", Rejected: "gray" }[doc.status] || "gray";
		return [__(doc.status), colour, "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_action_item(__("Print ID Cards"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) return frappe.msgprint(__("Tick the members whose cards you want."));
			window.open("/library/card?patron=" + names.map(encodeURIComponent).join(","), "_blank");
		});
	},
};
