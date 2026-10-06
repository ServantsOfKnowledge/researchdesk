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

	render(groups) {
		const esc = frappe.utils.escape_html;
		const jump = groups.map((g) => `<a href="#" data-jump="${esc(g.key)}">${esc(g.title)}</a>`).join("");
		const route = (a) => encodeURI(a.target.map((t) => encodeURIComponent(t)).join("/"));
		const action = (a, can) => {
			const cls = `btn btn-xs ${a.primary && can ? "btn-primary" : "btn-default"}`;
			if (!can) return `<span class="btn btn-xs btn-default disabled" aria-disabled="true">${esc(a.label)}</span>`;
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
