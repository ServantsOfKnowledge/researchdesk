// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// Settings → Features: data here that a switched-off feature would handle, with Turn On
function rd_feature_suggestions(frm) {
	const field = frm.fields_dict.feature_suggestions;
	if (!field) return;
	frappe.call("sok_resdesk.features.overview").then((r) => {
		const list = (r.message && r.message.suggestions) || [];
		if (!list.length) {
			field.$wrapper.html("");
			return;
		}
		const rows = list
			.map(
				(s) => `<div class="rd-feature-hint" style="display:flex;gap:12px;align-items:center;margin:6px 0">
					<span class="indicator-pill orange" style="flex:none">${frappe.utils.escape_html(s.label)}</span>
					<span style="flex:1;min-width:0">${frappe.utils.escape_html(s.why)}</span>
					<button class="btn btn-xs btn-default" data-feature="${frappe.utils.escape_html(s.feature)}">${__("Turn on")}</button></div>`
			)
			.join("");
		field.$wrapper.html(`<div class="form-message blue" style="margin-bottom:12px">
			<p><b>${__("Data here that a switched-off feature would use")}</b></p>${rows}</div>`);
		field.$wrapper.find("[data-feature]").on("click", (e) => {
			const feature = e.currentTarget.dataset.feature;
			frappe.call({ method: "sok_resdesk.features.switch_on", args: { feature }, freeze: true }).then(() => frm.reload_doc());
		});
	});
}

frappe.ui.form.on("RD Settings", {
	refresh(frm) {
		rd_feature_suggestions(frm);
		frm.add_custom_button(__("Find the Telegram Chat ID"), () =>
			frm.is_dirty() ? frappe.msgprint(__("Save Settings first: this uses the saved bot token.")) : frappe.call({ method: "sok_resdesk.contact.find_telegram_chat", freeze: true }).then((r) => {
				const m = r.message || {};
				if (!m.ok) return frappe.msgprint({ title: __("Telegram"), indicator: "red", message: frappe.utils.escape_html(m.why || __("Nothing found.")) });
				const list = "<ul>" + m.chats.map((c) => `<li>${frappe.utils.escape_html(c.label)}: <code>${frappe.utils.escape_html(c.id)}</code></li>`).join("") + "</ul>";
				// one chat is filled in; with several (a stranger may have written to a public bot) you choose
				if (m.chats.length === 1) {
					frm.set_value("telegram_chat_id", m.chats[0].id);
					return frappe.msgprint({ title: __("Telegram"), indicator: "green", message: __("The Chat ID is filled in for {0}. Check that this is you or your group, save Settings, then send the test message.", [frappe.utils.escape_html(m.chats[0].label)]) });
				}
				frappe.msgprint({ title: __("Telegram"), indicator: "orange", message: __("The bot has heard from several chats. Type the Chat ID of yours into the field, save, then send the test message. Anyone can write to a public bot, so choose carefully:") + list });
			}), __("Messages")
		);
		frm.add_custom_button(__("Send a Test Telegram Message"), () =>
			frm.is_dirty() ? frappe.msgprint(__("Save Settings first: the test uses the saved token and chat ID.")) : frappe.call({ method: "sok_resdesk.contact.test_telegram", freeze: true }).then((r) => {
				const m = r.message || {};
				frappe.msgprint({
					title: __("Telegram"),
					indicator: m.ok ? "green" : "red",
					message: m.ok ? __("Sent. Look in the chat for the test message.") : frappe.utils.escape_html(m.why || __("It was not sent.")),
				});
			}), __("Messages")
		);
		frm.add_custom_button(__("Test Search Engine"), () =>
			frappe.call({
				method: "sok_resdesk.search.setup_indexes",
				freeze: true,
				freeze_message: __("Connecting to Meilisearch…"),
				callback: (r) => {
					frappe.msgprint({ title: __("Search engine"), message: r.message, indicator: "green" });
					frm.reload_doc();
				},
			})
		);
		frm.add_custom_button(__("Rebuild Search Index"), () =>
			frappe.confirm(
				__("Re-index every catalogue record? Page text is fetched again from the Internet Archive, so this can take a while for large catalogues."),
				() =>
					frappe.call({
						method: "sok_resdesk.search.enqueue_rebuild",
						callback: () =>
							frappe.show_alert({ message: __("Rebuild queued"), indicator: "green" }),
					})
			)
		);
		frm.add_custom_button(__("Apply Access Rules"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Apply access rules to books already in the catalogue"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p>${__("Each book gets the visibility its ingest profile, the first matching rule or the default gives it. New books get this automatically; this updates the ones already here.")}</p>`,
					},
					{
						fieldname: "include_manual",
						fieldtype: "Check",
						label: __("Also change books whose visibility was set by hand or in bulk"),
					},
				],
				primary_action_label: __("Apply"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "sok_resdesk.access.apply_rules",
						args: { include_manual: values.include_manual ? 1 : 0 },
						callback: (r) => frappe.show_alert({ message: r.message.message, indicator: "green" }),
					});
				},
			});
			frm.is_dirty() ? frappe.msgprint(__("Save the settings first.")) : d.show();
		});
		frm.add_custom_button(__("Background Jobs"), () => frappe.set_route("resdesk-jobs"));
		if (frm.doc.preservation_root) {
			frm.add_custom_button(
				__("Make Every Second Copy Now"),
				() =>
					frappe.call("sok_resdesk.preservation.enqueue_second_copies").then((r) =>
						frappe.show_alert({ message: __("{0} books queued for their second copy", [r.message]), indicator: "green" })
					),
				__("Preservation")
			);
			frm.add_custom_button(
				__("BagIt Exports"),
				() =>
					frappe.call("sok_resdesk.preservation.exports").then((r) => {
						const rows = r.message || [];
						const esc = frappe.utils.escape_html;
						frappe.msgprint({
							title: __("BagIt Exports"),
							message: rows.length
								? `<p class="text-muted">${__("Kept for two weeks; make them again from a book or a collection.")}</p><ul>${rows
										.map(
											(x) =>
												`<li><a href="/api/method/sok_resdesk.preservation.download_export?file=${encodeURIComponent(x.file)}">${esc(x.file)}</a> · ${frappe.form.formatters.Float(x.bytes / 1048576, { precision: 1 })} MB · ${esc(x.made)}</li>`
										)
										.join("")}</ul>`
								: __("No exports yet: Export BagIt on a book or a collection makes one."),
						});
					}),
				__("Preservation")
			);
		}
		frm.add_custom_button(__("Reader Requests"), () => frappe.set_route("List", "RD Reader Request", { status: "Pending" }));
		frm.add_web_link("/", __("Open Portal"));
	},
});
