// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE

// One record per person: opening the list goes to my own, and the form connects and disconnects.
frappe.ui.form.on("RD Wikimedia Account", {
	refresh(frm) {
		frm.disable_save();
		const esc = frappe.utils.escape_html;
		frappe.call("sok_resdesk.wikimedia.status").then((r) => {
			const s = r.message;
			frm.dashboard.clear_headline();
			if (s.connected) {
				frm.dashboard.set_headline_alert(
					__("Connected as {0} on Wikimedia. What you give back to Wikidata is sent under this account.", [`<b>${esc(s.wikimedia_user)}</b>`]),
					"green"
				);
				frm.add_custom_button(__("Reconnect with a New Token"), () => connect(frm));
				frm.add_custom_button(__("Disconnect"), () =>
					frappe.confirm(__("Forget your access token here? You can also revoke the consumer on Wikimedia."), () =>
						frappe.call("sok_resdesk.wikimedia.disconnect").then(() => frappe.set_route("List", "RD Wikimedia Account"))
					)
				);
			} else {
				frm.dashboard.set_headline_alert(__("Not connected yet."), "orange");
				frm.page.set_primary_action(__("Connect"), () => connect(frm));
			}
			frm.set_intro(
				`<p>${__("Wikimedia credits edits to the person who made them, so each person connects their own account here. You do it once: register a personal OAuth 2.0 consumer on Wikimedia, then paste its access token.")}</p>` +
					`<ol>${s.steps.map((t) => `<li>${t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</li>`).join("")}</ol>` +
					`<p><a href="${esc(s.register_url)}" target="_blank" rel="noopener">${__("Register a consumer on Wikimedia")} ↗</a></p>` +
					`<p class="text-muted">${__("The token is kept encrypted and is only ever used for edits you ask for. Nobody else, administrators included, can read or use it.")}</p>`,
				"blue"
			);
		});
	},
});

function connect(frm) {
	frappe.prompt(
		[{ fieldname: "token", fieldtype: "Password", label: __("Access Token"), reqd: 1 }],
		(v) =>
			frappe
				.call({ method: "sok_resdesk.wikimedia.connect", args: { token: v.token }, freeze: true, freeze_message: __("Asking Wikimedia…") })
				.then((r) => {
					frappe.show_alert({ message: __("Connected as {0}", [r.message.wikimedia_user]), indicator: "green" }, 7);
					// the saved record (the form may have been a new, unsaved one)
					window.location.href = `/app/rd-wikimedia-account/${encodeURIComponent(frappe.session.user)}`;
				}),
		__("Connect your Wikimedia account"),
		__("Connect")
	);
}
