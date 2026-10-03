// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Items list: set who can see many books at once, either the ticked rows
// or everything that matches the current filters.

frappe.listview_settings["RD Item"] = {
	add_fields: ["visibility", "published"],
	get_indicator(doc) {
		if (!doc.published) return [__("Unpublished"), "gray", "published,=,0"];
		return {
			Public: [__("Public"), "green", "visibility,=,Public"],
			"Login to read": [__("Login to read"), "orange", "visibility,=,Login to read"],
			"Login to find": [__("Login to find"), "red", "visibility,=,Login to find"],
		}[doc.visibility || "Public"];
	},
	onload(listview) {
		// OCR quality: sort by it (lowest first) to find the books that most need better text
		listview.page.add_menu_item(__("Score OCR quality"), () =>
			frappe.call({ method: "sok_resdesk.ocr.enqueue_scoring", freeze: true }).then((r) =>
				frappe.show_alert({ message: __("{0} books are being scored in the background.", [r.message]), indicator: "green" })
			)
		);
		const ask = (label, args, count) => {
			const d = new frappe.ui.Dialog({
				title: label,
				fields: [
					{
						fieldname: "visibility",
						fieldtype: "Select",
						label: __("Who can see them"),
						options: ["Public", "Login to read", "Login to find"],
						default: "Login to read",
						reqd: 1,
						description: __(
							"Public: anyone can find and read. Login to read: anyone can find and cite; reading needs a login. Login to find: only logged-in readers can find them."
						),
					},
				],
				primary_action_label: count ? __("Apply to {0} books", [count]) : __("Apply"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "sok_resdesk.access.bulk_set_visibility",
						args: { visibility: values.visibility, ...args },
						freeze: true,
						freeze_message: __("Updating…"),
						callback: (r) => {
							frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
							listview.refresh();
						},
					});
				},
			});
			d.show();
		};

		const collection_dialog = (label, args, count) => {
			const d = new frappe.ui.Dialog({
				title: label,
				fields: [
					{ fieldname: "action", fieldtype: "Select", label: __("Action"), options: [
						{ value: "add", label: __("Add to collection") },
						{ value: "remove", label: __("Remove from collection") },
					], default: "add" },
					{ fieldname: "collection", fieldtype: "Link", options: "RD Collection", label: __("Collection"), reqd: 1,
					  description: __("Type a new name and choose “Create a new RD Collection” to make one.") },
				],
				primary_action_label: count ? __("Apply to {0} books", [count]) : __("Apply"),
				primary_action(v) {
					d.hide();
					frappe.call({
						method: "sok_resdesk.curation.bulk",
						args: { action: v.action, collection: v.collection, ...args },
						freeze: true,
						callback: (r) => {
							frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
							listview.refresh();
						},
					});
				},
			});
			d.show();
		};
		listview.page.add_actions_menu_item(__("Add to / Remove from Collection"), () => {
			const names = listview.get_checked_items(true);
			collection_dialog(__("Selected books"), { names: JSON.stringify(names) }, names.length);
		});
		listview.page.add_menu_item(__("Add All Matching Books to a Collection"), () => {
			const filters = listview.get_filters_for_args();
			frappe.db.count("RD Item", { filters }).then((count) =>
				collection_dialog(__("Books matching the current filters"), filters.length ? { filters: JSON.stringify(filters) } : { everything: 1 }, count)
			);
		});
		listview.page.add_menu_item(__("Export Metadata of Matching Books"), () =>
			frappe.new_doc("RD Export", { scope: "Filters", filters_json: JSON.stringify(listview.get_filters_for_args()) })
		);

		listview.page.add_actions_menu_item(__("Set Who Can See Them"), () => {
			const names = listview.get_checked_items(true);
			ask(__("Selected books"), { names: JSON.stringify(names) }, names.length);
		});

		listview.page.add_menu_item(__("Set Who Can See All Matching Books"), () => {
			const filters = listview.get_filters_for_args();
			frappe.db.count("RD Item", { filters }).then((count) => {
				if (!filters.length) {
					frappe.confirm(__("No filter is set: this changes all {0} books. Continue?", [count]), () =>
						ask(__("All books"), { everything: 1 }, count)
					);
				} else {
					ask(__("Books matching the current filters"), { filters: JSON.stringify(filters) }, count);
				}
			});
		});
	},
};
