// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Connections: every outside system Research Desk works with, by kind: what it does, whether it is
// on or connected for me, who may use it, and where to open it (sok_resdesk/connections.py).

frappe.pages["resdesk-connections"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Connections"), single_column: true });
	wrapper.resdesk_connections = new ResDeskConnections(page);
};

frappe.pages["resdesk-connections"].on_page_show = function (wrapper) {
	wrapper.resdesk_connections && wrapper.resdesk_connections.refresh();
};

class ResDeskConnections {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="rdc"></div>').appendTo(page.main);
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		page.add_menu_item(__("Settings → Features"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/staff-guide") : frappe.set_route("resdesk-help", "staff-guide")
		);
		this.$body.on("click", "[data-route]", (e) => {
			e.preventDefault();
			frappe.set_route(...String($(e.currentTarget).data("route")).split("/").map(decodeURIComponent));
		});
		this.$body.on("click", "[data-email]", (e) => {
			e.preventDefault();
			this.mail_dialog();
		});
		this.$body.on("click", "[data-copy]", (e) => {
			e.preventDefault();
			frappe.utils.copy_to_clipboard($(e.currentTarget).data("copy"));
		});
		this.$body.on("click", "[data-jump]", (e) => {
			e.preventDefault();
			const el = this.$body.find(`#rdc-${$(e.currentTarget).data("jump")}`)[0];
			if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
		});
		this.$body.append(`<style>
			.rdc { padding: 4px 0 40px; }
			.rdc-lead { max-width: 60em; margin: 4px 0 12px; }
			.rdc-jump { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }
			.rdc-jump a { padding: 4px 12px; border: 1px solid var(--border-color); border-radius: 999px; color: var(--text-color); text-decoration: none; }
			.rdc-group { margin: 26px 0 8px; scroll-margin-top: 70px; }
			.rdc-group h3 { margin: 0; font-size: 1.15rem; }
			.rdc-group p { margin: 2px 0 0; }
			.rdc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; margin-top: 10px; }
			.rdc-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 14px; background: var(--card-bg); display: flex; flex-direction: column; gap: 8px; }
			.rdc-card h4 { margin: 0; font-size: 1rem; }
			.rdc-card p { margin: 0; color: var(--text-color); }
			.rdc-chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid transparent; }
			.rdc-ok { background: #d8f0dd; color: #14461f; }
			.rdc-todo { background: #fde8c8; color: #5a3200; }
			.rdc-off { background: #e6e6e6; color: #333; }
			.rdc-info { background: #dde8f7; color: #16325c; }
			.rdc-who { font-size: 13px; color: var(--text-color); opacity: .85; }
			.rdc-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
			.rdc-urls { font-size: 12px; word-break: break-all; }
			.rdc-locked { opacity: .75; }
		</style>`);
		this.$out = $('<div></div>').appendTo(this.$body);
	}

	refresh() {
		frappe.call("sok_resdesk.connections.overview").then((r) => this.render(r.message || []));
	}

	mail_dialog() {
		frappe.call("sok_resdesk.mail.status").then((r) => {
			const m = r.message || {};
			const cur = m.settings || {};
			const d = new frappe.ui.Dialog({
				title: __("Outgoing email"),
				fields: [
					{ fieldtype: "HTML", options: `<p class="text-muted small">${__("The mailbox Research Desk sends sign-in, sign-up and password emails from. Gmail and Microsoft need an app password, not your normal one.")}</p>${m.failed ? `<div class="alert alert-warning small"><b>${__("{0} earlier emails failed to send.", [m.failed])}</b> ${frappe.utils.escape_html(m.last_error || "")}<br>${__("This is the error from the earlier try, not from your new settings. Save and send the test: once it works the failed emails are sent again.")}</div>` : ""}` },
					{ fieldname: "preset", label: __("Mail provider"), fieldtype: "Select", options: (m.presets || []).map((p) => p.label).join("\n"),
						change: () => { const p = (m.presets || []).find((x) => x.label === d.get_value("preset")); if (p) { d.set_value("smtp_server", p.server); d.set_value("smtp_port", p.port); d.set_value("security", p.security); if (p.login) d.set_value("login_id", p.login); } } },
					{ fieldname: "email_id", label: __("Send from (address)"), fieldtype: "Data", reqd: 1, default: cur.email_id },
					{ fieldname: "smtp_server", label: __("Mail server"), fieldtype: "Data", reqd: 1, default: cur.smtp_server },
					{ fieldname: "smtp_port", label: __("Port"), fieldtype: "Int", default: cur.smtp_port || 587 },
					{ fieldname: "security", label: __("Security"), fieldtype: "Select", options: "tls\nssl\nnone", default: cur.use_ssl_for_outgoing ? "ssl" : cur.use_tls === 0 ? "none" : "tls", description: __("tls = STARTTLS (587), ssl = SSL (465)") },
					{ fieldname: "login_id", label: __("Sign-in name (if not the address)"), fieldtype: "Data", default: cur.login_id },
					{ fieldname: "password", label: __("Password or app password"), fieldtype: "Password", description: m.ready ? __("Leave empty to keep the saved one") : "" },
					{ fieldname: "forget", label: __("Forget the failed emails"), fieldtype: "Button", hidden: m.failed ? 0 : 1, click: () => frappe.call("sok_resdesk.mail.clear_failed").then((r) => { frappe.show_alert({ message: r.message.message, indicator: "green" }); d.hide(); this.refresh(); }) },
					{ fieldname: "to", label: __("Send a test to"), fieldtype: "Data", default: frappe.session.user_email },
				],
				primary_action_label: __("Save and send test"),
				primary_action: (v) => {
					frappe.call({ method: "sok_resdesk.mail.save", args: { email_id: v.email_id, smtp_server: v.smtp_server, smtp_port: v.smtp_port, login_id: v.login_id || "", password: v.password || "", security: v.security } })
						.then(() => frappe.call("sok_resdesk.mail.test", { to: v.to }))
						.then((t) => {
							const x = t.message || {};
							frappe.msgprint({ title: x.ok ? __("Email works") : __("Email did not send"), message: frappe.utils.escape_html(x.message || ""), indicator: x.ok ? "green" : "red" });
							if (x.ok) { d.hide(); this.refresh(); if (m.failed) frappe.call("sok_resdesk.mail.retry_failed").then((q) => frappe.msgprint({ title: __("Failed emails"), message: frappe.utils.escape_html((q.message || {}).message || ""), indicator: "blue" })); }
						});
				},
			});
			d.show();
		});
	}

	render(groups) {
		const esc = frappe.utils.escape_html;
		const jump = groups.map((g) => `<a href="#" data-jump="${esc(g.key)}">${esc(g.title)}</a>`).join("");
		const route = (a) => a.target.map((t) => encodeURIComponent(t)).join("/");
		const action = (a, can) => {
			const cls = `btn btn-xs ${a.primary && can ? "btn-primary" : "btn-default"}`;
			if (!can) return `<span class="btn btn-xs btn-default disabled" aria-disabled="true">${esc(a.label)}</span>`;
			if (a.kind === "email") return `<a class="${cls}" href="#" data-email="1">${esc(a.label)}</a>`;
			return a.kind === "url"
				? `<a class="${cls}" href="${esc(a.target)}" target="_blank" rel="noopener">${esc(a.label)} ↗</a>`
				: `<a class="${cls}" href="#" data-route="${route(a)}">${esc(a.label)}</a>`;
		};
		const card = (c) => `
			<div class="rdc-card ${c.can ? "" : "rdc-locked"}">
				<h4>${esc(c.title)}</h4>
				<div><span class="rdc-chip rdc-${esc(c.status.state)}">${esc(c.status.text)}</span></div>
				<p>${esc(c.what)}</p>
				<div class="rdc-who">${__("Who")}: ${esc(c.who)}${c.can || !c.actions.length ? "" : " · " + __("not available to your role")}</div>
				${c.urls.length ? `<div class="rdc-urls">${c.urls.map((u) => `${esc(u.label)}: <a href="#" data-copy="${esc(u.url)}" title="${__("Copy the address")}">${esc(u.url)}</a>`).join("<br>")}</div>` : ""}
				<div class="rdc-acts">${c.actions.map((a) => action(a, c.can)).join("")}</div>
			</div>`;
		const group = (g) => `
			<section class="rdc-group" id="rdc-${esc(g.key)}" aria-labelledby="rdc-h-${esc(g.key)}">
				<h3 id="rdc-h-${esc(g.key)}">${esc(g.title)}</h3>
				<p>${esc(g.what)}</p>
				<div class="rdc-grid">${g.cards.map(card).join("")}</div>
			</section>`;
		this.$out.html(
			`<p class="rdc-lead">${__("Everything Research Desk shares with, or takes from, other systems, by kind. A grey, disabled button means your role does not use it; a grey chip means the feature is switched off in Settings → Features.")}</p>` +
				`<nav class="rdc-jump" aria-label="${__("Kinds of connection")}">${jump}</nav>` +
				groups.map(group).join("")
		);
	}
}
