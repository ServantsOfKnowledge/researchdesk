// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Install Notes: the installations that have told this site (the registry) that they exist: how many, which
// versions, what kinds of institution, and the list. Only on research.servantsofknowledge.in, where
// Settings → Install Note → "This Site Is the Registry" is ticked. No addresses are kept (docs/install-count.md).

frappe.pages["resdesk-install-notes"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Install Notes"), single_column: true });
	const $body = $('<div class="rdi"></div>').appendTo(page.main);
	const esc = frappe.utils.escape_html;
	const card = (v, l) => `<div class="frappe-card" style="padding:12px 18px;min-width:130px"><div style="font-size:24px;font-weight:600">${v}</div><div>${esc(l)}</div></div>`;
	const counts = (title, o) => {
		const rows = Object.entries(o || {}).sort((a, b) => b[1] - a[1]);
		return `<div style="flex:1;min-width:200px"><h5>${esc(title)}</h5>${rows.length ? `<table class="table table-sm"><tbody>${rows.map(([k, n]) => `<tr><td>${esc(k)}</td><td style="text-align:right">${n}</td></tr>`).join("")}</tbody></table>` : `<p class="text-muted">–</p>`}</div>`;
	};
	const load = () => {
		$body.html(`<p class="text-muted" role="status">${__("Counting…")}</p>`);
		return Promise.all([frappe.call("sok_resdesk.registry.summary"), frappe.call("sok_resdesk.registry.recent", { limit: 200 })]).then(([s, r]) => {
			const d = s.message, rows = r.message || [];
			if (!d.receiving) {
				$body.html(`<p>${__("This site is not the registry. Tick Settings → Install Note → This Site Is the Registry on research.servantsofknowledge.in to take install notes here.")}</p>`);
				return;
			}
			$body.html(`
				<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px">${card(d.active, __("Still sending (last 45 days)"))}${card(d.ever, __("Heard from, ever"))}</div>
				<div style="display:flex;gap:24px;flex-wrap:wrap">${counts(__("Versions"), d.versions)}${counts(__("Edition"), d.editions)}${counts(__("Installed as"), d.kinds)}${counts(__("Kinds of institution"), d.profiles)}</div>
				<h5 style="margin-top:16px">${__("The most recent installs")}</h5>
				${rows.length ? `<table class="table table-sm"><thead><tr><th scope="col">${__("Install ID")}</th><th scope="col">${__("Version")}</th><th scope="col">${__("Edition")}</th><th scope="col">${__("Installed as")}</th><th scope="col">${__("Kinds of institution")}</th><th scope="col">${__("First heard")}</th><th scope="col">${__("Last heard")}</th><th scope="col" style="text-align:right">${__("Notes")}</th></tr></thead><tbody>${rows
					.map((x) => `<tr><td><code>${esc(x.instance_id.slice(0, 8))}</code></td><td>${esc(x.version)}</td><td>${esc(x.edition)}</td><td>${esc(x.kind)}</td><td>${esc((x.profiles || "").split(",").join(", "))}</td><td>${esc(x.first_seen)}</td><td>${esc(x.last_seen)}</td><td style="text-align:right">${x.pings}</td></tr>`)
					.join("")}</tbody></table>` : `<p class="text-muted">${__("No notes yet.")}</p>`}`);
		});
	};
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");
	page.add_menu_item(__("Open the full list"), () => frappe.set_route("List", "RD Install Ping"));
	load();
};
