// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Portal Statistics: how readers use the portal (Settings → Usage Statistics → Built-in). Counted here, when
// this page is opened, and kept for ten minutes, so the Research Desk dashboard never waits for the page-view log.

frappe.pages["resdesk-statistics"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Portal Statistics"), single_column: true });
	const $body = $('<div class="rds"></div>').appendTo(page.main);
	const esc = frappe.utils.escape_html;
	let days = 30;
	const draw = (d) => {
		if (d.provider !== "Built-in") {
			$body.html(`<p>${d.provider === "Off" ? __("Usage statistics are switched off. Choose Built-in under Settings → Usage Statistics to count page views here.") : esc(__("Statistics are kept in {0}.", [d.provider]))}</p>
				${d.dashboard ? `<p><a class="btn btn-default btn-sm" href="${esc(d.dashboard)}" target="_blank" rel="noopener">${__("Open the dashboard")}</a></p>` : ""}`);
			return;
		}
		const max = Math.max(1, ...d.by_day.map((r) => r.views));
		$body.html(`
			<p class="text-muted">${__("The last {0} days, as of {1}.", [d.days, esc(d.as_of)])}</p>
			<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px">
				<div class="frappe-card" style="padding:12px 18px"><div style="font-size:24px;font-weight:600">${d.views}</div><div>${__("Page views")}</div></div>
				<div class="frappe-card" style="padding:12px 18px"><div style="font-size:24px;font-weight:600">${d.visitors}</div><div>${__("Visitors")}</div></div>
			</div>
			<h5>${__("Most-read books")}</h5>
			${d.top.length ? `<table class="table table-sm"><thead><tr><th scope="col">${__("Book")}</th><th scope="col" style="text-align:right">${__("Views")}</th></tr></thead><tbody>${d.top
				.map((t) => `<tr><td><a href="/library/item/${encodeURIComponent(t.item)}" target="_blank" rel="noopener">${esc(t.title)}</a></td><td style="text-align:right">${t.views}</td></tr>`)
				.join("")}</tbody></table>` : `<p class="text-muted">${__("No book pages were viewed in this time.")}</p>`}
			<h5>${__("Views a day")}</h5>
			${d.by_day.length ? `<table class="table table-sm"><thead><tr><th scope="col">${__("Day")}</th><th scope="col">${__("Views")}</th></tr></thead><tbody>${d.by_day
				.map((r) => `<tr><td>${esc(r.day)}</td><td><span aria-hidden="true" style="display:inline-block;height:10px;width:${Math.round((r.views / max) * 240)}px;background:var(--primary);border-radius:3px;margin-right:8px"></span>${r.views}</td></tr>`)
				.join("")}</tbody></table>` : `<p class="text-muted">${__("Nothing yet.")}</p>`}`);
	};
	const load = (refresh) => {
		$body.html(`<p class="text-muted" role="status">${__("Counting…")}</p>`);
		return frappe.call({ method: "sok_resdesk.analytics.statistics", args: { days, refresh: refresh || 0 } }).then((r) => r.message && draw(r.message));
	};
	[7, 30, 90].forEach((n) => page.add_inner_button(__("{0} days", [n]), () => { days = n; load(0); }));
	page.set_secondary_action(__("Refresh"), () => load(1), "refresh");
	load(0);
};
