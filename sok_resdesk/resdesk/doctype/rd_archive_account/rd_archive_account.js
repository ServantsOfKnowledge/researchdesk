// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// One record per person: the form connects and disconnects my archive.org keys.
frappe.ui.form.on("RD Archive Account", {
	refresh(frm) {
		frm.disable_save();
		const esc = frappe.utils.escape_html;
		frappe.call("sok_resdesk.archive_upload.status").then((r) => {
			const s = r.message;
			frm.dashboard.clear_headline();
			if (s.connected) {
				frm.dashboard.set_headline_alert(
					__("Connected as {0} on archive.org. Books you send are uploaded under this account.", [`<b>${esc(s.ia_user)}</b>`]),
					"green"
				);
				frm.add_custom_button(__("Reconnect with New Keys"), () => connect());
				frm.add_custom_button(__("Disconnect"), () =>
					frappe.confirm(__("Forget your keys here? You can also make new ones on archive.org."), () =>
						frappe.call("sok_resdesk.archive_upload.disconnect").then(() => frappe.set_route("List", "RD Archive Account"))
					)
				);
			} else {
				frm.dashboard.set_headline_alert(__("Not connected yet."), "orange");
				frm.page.set_primary_action(__("Connect"), () => connect());
			}
			frm.set_intro(
				`<p>${__("To give a book to the Internet Archive you need an archive.org account. Paste the account's S3-like access keys here once.")}</p>` +
					`<ol>${s.steps.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>` +
					`<p><a href="${esc(s.keys_url)}" target="_blank" rel="noopener">${__("Get your keys on archive.org")} ↗</a></p>` +
					`<p class="text-muted">${__("The keys are kept encrypted and are only used for uploads you ask for. Everything sent is public on archive.org.")}</p>`,
				"blue"
			);
		});
	},
});

function connect() {
	frappe.prompt(
		[
			{ fieldname: "access", fieldtype: "Data", label: __("Access Key"), reqd: 1 },
			{ fieldname: "secret", fieldtype: "Password", label: __("Secret Key"), reqd: 1 },
		],
		(v) =>
			frappe
				.call({ method: "sok_resdesk.archive_upload.connect", args: v, freeze: true, freeze_message: __("Asking archive.org…") })
				.then((r) => {
					frappe.show_alert({ message: __("Connected as {0}", [r.message.ia_user]), indicator: "green" }, 7);
					window.location.href = `/app/rd-archive-account/${encodeURIComponent(frappe.session.user)}`;
				}),
		__("Connect your archive.org account"),
		__("Connect")
	);
}
