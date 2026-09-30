// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Help: the Research Desk documentation (docs/*.md) inside the Desk.
// /app/resdesk-help/<page>#<section>

frappe.pages["resdesk-help"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Help"), single_column: true });
	wrapper.resdesk_help = new ResDeskHelp(page, wrapper);
};

frappe.pages["resdesk-help"].on_page_show = function (wrapper) {
	wrapper.resdesk_help && wrapper.resdesk_help.show();
};

class ResDeskHelp {
	constructor(page, wrapper) {
		this.page = page;
		this.$body = $('<div class="rdh"></div>').appendTo(page.main);
		page.set_secondary_action(__("Open the portal help"), () => window.open("/library/help"));
		page.add_menu_item(__("Restart the getting-started checklist"), () =>
			frappe.call("sok_resdesk.guide.restart_checklist").then(() => frappe.set_route("research-desk"))
		);
		page.add_menu_item(__("Documentation on GitHub"), () =>
			window.open("https://github.com/ServantsOfKnowledge/researchdesk/tree/main/docs")
		);
		// links inside the help stay inside the Desk
		this.$body.on("click", "a", (e) => {
			const href = e.currentTarget.getAttribute("href") || "";
			if (href.startsWith("/app/resdesk-help/")) {
				e.preventDefault();
				const [path, anchor] = href.split("#");
				const slug = path.split("/").pop();
				if (slug === this.slug) return this.scroll_to(anchor);
				this.anchor = anchor;
				frappe.set_route("resdesk-help", slug);
			} else if (href.startsWith("#")) {
				e.preventDefault();
				this.scroll_to(href.slice(1));
			}
		});
	}

	show() {
		const route = frappe.get_route();
		const slug = route[1] || "staff-guide";
		const anchor =
			this.anchor || (frappe.route_options && frappe.route_options.section) || decodeURIComponent((window.location.hash || "").slice(1));
		this.anchor = null;
		frappe.route_options = null;
		if (slug === this.slug && this.html_ready) return this.scroll_to(anchor);
		this.slug = slug;
		frappe.call({ method: "sok_resdesk.help.get_page", args: { slug } }).then((r) => {
			this.render(r.message);
			this.scroll_to(anchor);
		});
	}

	scroll_to(anchor) {
		if (!anchor) return window.scrollTo(0, 0);
		const el = document.getElementById(anchor);
		if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	render(p) {
		const esc = frappe.utils.escape_html;
		this.page.set_title(p.title);
		const nav = p.index
			.map(
				(g) => `<h6>${esc(g.group)}</h6><ul>${g.pages
					.map(
						(x) =>
							`<li><a href="/app/resdesk-help/${x.slug}" class="${x.slug === p.slug ? "active" : ""}">${esc(x.title)}</a></li>`
					)
					.join("")}</ul>`
			)
			.join("");
		const toc = p.toc.length
			? `<h6>${__("On this page")}</h6><ul>${p.toc
					.map((h) => `<li class="rdh-toc-${h.level}"><a href="#${h.anchor}">${esc(frappe.utils.html2text(h.text))}</a></li>`)
					.join("")}</ul>`
			: "";
		this.$body.html(`
			<style>
				.rdh { display:grid; grid-template-columns: 250px minmax(0,1fr); gap: 28px; padding: 8px 0 60px; }
				.rdh-nav { position: sticky; top: 70px; align-self: start; max-height: calc(100vh - 90px); overflow:auto; font-size: 13px; }
				.rdh-nav h6 { text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); margin: 16px 0 6px; font-size: 11px; }
				.rdh-nav ul { list-style:none; padding:0; margin:0; }
				.rdh-nav li { margin: 3px 0; }
				.rdh-nav a.active { font-weight: 600; color: var(--primary); }
				.rdh-toc-3 { padding-left: 12px; }
				.rdh-body { max-width: 80ch; font-size: 14px; line-height: 1.6; }
				.rdh-body h1 { font-size: 1.7rem; margin: 0 0 12px; }
				.rdh-body h2 { font-size: 1.3rem; margin: 30px 0 10px; padding-top: 10px; border-top: 1px solid var(--border-color); scroll-margin-top: 70px; }
				.rdh-body h3 { font-size: 1.08rem; margin: 22px 0 8px; scroll-margin-top: 70px; }
				.rdh-body table { margin: 12px 0; font-size: 13px; }
				.rdh-body pre { background: var(--subtle-fg); padding: 12px; border-radius: 8px; overflow: auto; }
				.rdh-body img { max-width: 100%; height: auto; border: 1px solid var(--border-color); border-radius: 8px; margin: 8px 0; }
				@media (max-width: 900px) { .rdh { grid-template-columns: 1fr; } .rdh-nav { position: static; max-height: none; } }
			</style>
			<aside class="rdh-nav">${nav}${toc}</aside>
			<article class="rdh-body">${p.html}</article>`);
		this.html_ready = true;
	}
}
