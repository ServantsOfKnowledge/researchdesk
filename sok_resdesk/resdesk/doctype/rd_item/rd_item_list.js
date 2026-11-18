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
			"Approval to read": [__("Approval to read"), "purple", "visibility,=,Approval to read"],
		}[doc.visibility || "Public"];
	},
	onload(listview) {
		listview.page.add_menu_item(__("Re-OCR the worst books"), () =>
			frappe.call({ method: "sok_resdesk.reocr.engine_status" }).then((r) => {
				if (!r.message.installed) return frappe.msgprint(__("The OCR engine (Tesseract) isn't installed on this server."));
				frappe.prompt(
					[
						{ fieldname: "count", fieldtype: "Int", label: __("How many books"), default: 20 },
						{ fieldname: "preset", fieldtype: "Select", label: __("Layout of the pages"), options: r.message.presets, default: "Whole page" },
					],
					(v) =>
						frappe.call({ method: "sok_resdesk.reocr.enqueue_worst", args: v }).then((x) =>
							frappe.show_alert({ message: x.message.message, indicator: "green" })
						),
					__("Re-OCR the books with the worst text"),
					__("Start")
				);
			})
		);
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
						options: ["Public", "Login to read", "Login to find", "Approval to read"],
						default: "Login to read",
						reqd: 1,
						description: __(
							"Public: anyone can find and read. Login to read: anyone can find and cite; reading needs a login. Approval to read: anyone can find and cite; reading needs a login and a librarian's approval of each reader. Login to find: only logged-in readers can find them."
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
		// the books ticked in the list (the checkboxes allow as many as the list shows)
		const picked = () => {
			const names = listview.get_checked_items(true);
			if (!names.length) frappe.msgprint(__("Tick the books first."));
			return names;
		};
		listview.page.add_actions_menu_item(__("Add to / Remove from Collection"), () => {
			const names = picked();
			if (!names.length) return;
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

		// only where the governance app is installed
		if ((frappe.boot.user.can_read || []).includes("RD Department")) listview.page.add_actions_menu_item(__("Set Classification"), () => {
			const names = listview.get_checked_items(true);
			const d = new frappe.ui.Dialog({
				title: __("Set Classification"),
				fields: [
					{ fieldname: "level", fieldtype: "Select", label: __("Level"), reqd: 1, default: "Unclassified", options: ["Unclassified", "Restricted", "Confidential", "Secret", "Top Secret"] },
					{ fieldname: "department", fieldtype: "Link", label: __("Department"), options: "RD Department", description: __("Empty: any person cleared for the level.") },
				],
				primary_action_label: __("Apply to {0} records", [names.length]),
				primary_action: (v) => {
					d.hide();
					frappe.call({
						method: "sok_resdesk_governance.classification.set_classification",
						args: { level: v.level, department: v.department || "", names: JSON.stringify(names) },
						freeze: true,
						callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }, 7),
					});
				},
			});
			d.show();
		});

		// reading the contents of many books at once is for managers; librarians check what it finds
		if (frappe.user.has_role(["System Manager", "SOK Super Admin", "ResDesk Manager"])) {
			const read_details = (args, count, label) =>
				frappe.confirm(__("Read publisher, place, year and ISBN from the title pages of {0} ({1} books)? Drafts appear in Metadata Suggestions for staff to check and apply.", [label, count]), () =>
					frappe.call({
						method: "sok_resdesk.frontmatter.bulk",
						args,
						freeze: true,
						callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }, 9),
					})
				);
			listview.page.add_actions_menu_item(__("Read Details From the Title Pages"), () => {
				const names = picked();
				if (names.length) read_details({ names: JSON.stringify(names) }, names.length, __("the selected books"));
			});
			listview.page.add_menu_item(__("Read Title-Page Details of All Matching Books"), () => {
				const filters = listview.get_filters_for_args();
				frappe.db.count("RD Item", { filters }).then((count) =>
					read_details(filters.length ? { filters: JSON.stringify(filters) } : { everything: 1 }, count, filters.length ? __("the books matching the filters") : __("all books"))
				);
			});
			const read_contents = (args, count, label) =>
				frappe.confirm(__("Read the contents of {0} ({1} books)? Drafts appear in Book Contents for staff to check and publish.", [label, count]), () =>
					frappe.call({
						method: "sok_resdesk.contents.bulk",
						args,
						freeze: true,
						callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }, 9),
					})
				);
			listview.page.add_actions_menu_item(__("Read the Contents"), () => {
				const names = picked();
				if (names.length) read_contents({ names: JSON.stringify(names) }, names.length, __("the selected books"));
			});
			listview.page.add_menu_item(__("Read the Contents of All Matching Books"), () => {
				const filters = listview.get_filters_for_args();
				frappe.db.count("RD Item", { filters }).then((count) =>
					read_contents(filters.length ? { filters: JSON.stringify(filters) } : { everything: 1 }, count, filters.length ? __("the books matching the filters") : __("all books"))
				);
			});
		}

		// who sees a book is decided by managers: cataloguers get neither action
		if (frappe.user.has_role(["System Manager", "SOK Super Admin", "ResDesk Manager"])) {
			listview.page.add_actions_menu_item(__("Mark Public"), () => {
				const names = picked();
				if (!names.length) return;
				frappe.confirm(__("Make {0} books public?", [names.length]), () =>
					frappe.call({
						method: "sok_resdesk.access.bulk_set_visibility",
						args: { visibility: "Public", names: JSON.stringify(names) },
						freeze: true,
						freeze_message: __("Updating…"),
						callback: (r) => {
							frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
							listview.refresh();
						},
					})
				);
			});

			listview.page.add_actions_menu_item(__("Set Who Can See Them"), () => {
				const names = picked();
				if (!names.length) return;
				ask(__("Selected books"), { names: JSON.stringify(names) }, names.length);
			});

			// how a book can be used (Full, Read only, Research only): also decided by managers
			const set_use = (args, count, label) => {
				const d = new frappe.ui.Dialog({
					title: __("How {0} can be used", [label]),
					fields: [
						{
							fieldname: "use_level",
							fieldtype: "Select",
							label: __("How they can be used"),
							options: ["Full", "Read only", "Research only"],
							default: "Read only",
							reqd: 1,
							description: __(
								"Full: read and download. Read only: read page by page, no PDF, text or image download. Research only: read only, and the text can be searched but not copied or downloaded. Staff are not limited."
							),
						},
					],
					primary_action_label: __("Apply to {0} books", [count]),
					primary_action(values) {
						d.hide();
						frappe.call({
							method: "sok_resdesk.access.bulk_set_use_level",
							args: { ...args, use_level: values.use_level },
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
			listview.page.add_actions_menu_item(__("Set How They Can Be Used"), () => {
				const names = picked();
				if (names.length) set_use({ names: JSON.stringify(names) }, names.length, __("the selected books"));
			});
			listview.page.add_menu_item(__("Set How All Matching Books Can Be Used"), () => {
				const filters = listview.get_filters_for_args();
				frappe.db.count("RD Item", { filters }).then((count) =>
					set_use(filters.length ? { filters: JSON.stringify(filters) } : { everything: 1 }, count, filters.length ? __("the books matching the filters") : __("all books"))
				);
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
		}
	},
};
