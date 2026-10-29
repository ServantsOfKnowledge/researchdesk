// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Copy"] = {
	onload(listview) {
		listview.page.add_action_item(__("Print Barcode Labels"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) return frappe.msgprint(__("Tick the copies whose labels you want."));
			window.open("/library/labels?codes=" + names.map(encodeURIComponent).join(","), "_blank");
		});
	},
};
