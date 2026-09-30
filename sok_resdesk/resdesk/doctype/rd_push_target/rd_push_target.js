frappe.ui.form.on("RD Push Target", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Test Connection"), () =>
			frappe.call({
				method: "sok_resdesk.outbound.test_connection",
				args: { target: frm.doc.name },
				freeze: true,
				freeze_message: __("Connecting…"),
			}).then((r) => frappe.show_alert({ message: r.message.message, indicator: "green" }, 7))
		);
		const push = (dry) => {
			const d = new frappe.ui.Dialog({
				title: dry ? __("Dry Run") : __("Push Now"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p>${dry
							? __("Nothing is sent. The run log shows what would change for each book.")
							: __("Metadata of every book in scope is sent to {0} now. Books that have not changed since the last push are skipped.", [frappe.utils.escape_html(frm.doc.target_type)])}</p>`,
					},
					{ fieldname: "force", fieldtype: "Check", label: __("Send unchanged books again too") },
				],
				primary_action_label: dry ? __("Start Dry Run") : __("Push"),
				primary_action(v) {
					d.hide();
					frappe.call({
						method: "sok_resdesk.outbound.start",
						args: { target: frm.doc.name, force: v.force ? 1 : 0, dry_run: dry ? 1 : 0 },
					}).then((r) => frappe.set_route("Form", "RD Push Run", r.message));
				},
			});
			d.show();
		};
		frm.add_custom_button(__("Dry Run"), () => push(1), __("Push"));
		if (frm.doc.enabled) frm.add_custom_button(__("Push Now"), () => push(0), __("Push"));
		frm.add_custom_button(__("Runs"), () => frappe.set_route("List", "RD Push Run", { target: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Pushed Records"), () => frappe.set_route("List", "RD External Record", { target: frm.doc.name }), __("View"));
		if (frm.doc.dry_run && frm.doc.enabled)
			frm.dashboard.set_headline_alert(__("Dry Run is on: runs from this target only report what they would send."), "orange");
	},
});
