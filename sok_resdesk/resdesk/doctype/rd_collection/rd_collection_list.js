// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

frappe.listview_settings["RD Collection"] = {
	onload(listview) {
		// pictures for every collection that has none, from archive.org (in the background)
		listview.page.add_menu_item(__("Get Missing Images from archive.org"), () =>
			frappe.call({ method: "sok_resdesk.collectioncovers.get_missing" }).then(() =>
				frappe.show_alert({ message: __("Getting images in the background; reload in a minute."), indicator: "green" }, 7)
			)
		);
	},
};
