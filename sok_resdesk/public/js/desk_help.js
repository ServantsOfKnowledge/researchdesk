// Research Desk: a Help button (opens the right section of the in-app help) and, where there
// is one, "Take the tour" on every Research Desk screen. Links come from sok_resdesk/help.py.
(function () {
	const conf = () => (frappe.boot && frappe.boot.resdesk_help) || null;

	// "/app/resdesk-help/<page>#<section>" -> the Help page, scrolled to that section
	function open_help(url) {
		const [path, section] = url.split("#");
		frappe.route_options = section ? { section } : null;
		frappe.set_route("resdesk-help", path.split("/").pop());
	}
	window.rd_open_help = open_help;

	// The library's logo (RD Settings → Logo, or the Research Desk mark) in the Desk sidebar
	// header on Research Desk screens, instead of a letter.
	function brand_sidebar() {
		const brand = frappe.boot && frappe.boot.resdesk_brand;
		const header = document.querySelector(".sidebar-header");
		if (!brand || !brand.logo || !header) return;
		const title_el = header.querySelector(".header-title");
		const title = (title_el || {}).textContent || "";
		if (!/^\s*(ResDesk|Research Desk)\s*$/.test(title)) return;
		if (title.trim() === "ResDesk") title_el.textContent = __("Research Desk"); // the module's short name
		const box = header.querySelector(".header-logo");
		if (!box || box.dataset.rdLogo === brand.logo) return;
		box.innerHTML = "";
		const img = document.createElement("img");
		img.src = brand.logo;
		img.alt = brand.title || "Research Desk";
		img.style.cssText = "width:100%;height:100%;object-fit:contain;border-radius:6px;";
		box.appendChild(img);
		box.dataset.rdLogo = brand.logo;
		const bg = header.querySelector(".sidebar-item-icon");
		if (bg) bg.style.background = "transparent";
	}
	$(document).on("page-change", () => setTimeout(brand_sidebar, 50));
	frappe.router && frappe.router.on && frappe.router.on("change", () => setTimeout(brand_sidebar, 300));
	new MutationObserver(() => brand_sidebar()).observe(document.body, { childList: true, subtree: true });

	frappe.ui.form.on("*", {
		refresh(frm) {
			const c = conf();
			if (!c || !c.screens[frm.doctype]) return;
			frm.add_custom_button(__("Help for this screen"), () => open_help(c.screens[frm.doctype]), __("Help"));
			if (c.tours.includes(frm.doctype)) {
				frm.add_custom_button(__("Take the tour"), () => frm.tour.init({ tour_name: frm.doctype }).then(() => frm.tour.start()), __("Help"));
			}
			frm.add_custom_button(__("All help pages"), () => frappe.set_route("resdesk-help"), __("Help"));
		},
	});

	frappe.router && frappe.router.on && frappe.router.on("change", () => {
		const c = conf();
		const route = frappe.get_route();
		if (!c || !route || route[0] !== "List") return;
		const dt = route[1];
		if (!c.screens[dt]) return;
		setTimeout(() => {
			const lv = cur_list;
			if (!lv || lv.doctype !== dt || lv.__rd_help) return;
			lv.__rd_help = true;
			lv.page.add_menu_item(__("Help for this screen"), () => open_help(c.screens[dt]));
		}, 800);
	});

	// ---- getting-started checklist (workspace custom block "Research Desk Checklist") ------
	function start_step(step) {
		const a = step.action;
		const go = () => {
			frappe.route_hooks = {};
			if (a.tour || a.field) {
				frappe.route_hooks.after_load = (frm) => {
					if (a.field) frm.scroll_to_field(a.field);
					if (a.tour) frm.tour.init({ tour_name: a.tour }).then(() => frm.tour.start());
				};
			}
			frappe.set_route(...a.route);
		};
		if (step.mark_on_click) {
			frappe.call({ method: "sok_resdesk.guide.checklist_mark", args: { key: step.key, what: "done" } }).then(go);
		} else go();
	}

	// ---- the numbers at the top of the workspace (custom block "Research Desk Numbers") -------
	window.rd_numbers = function (root) {
		const box = root.querySelector(".rd-numbers");
		if (!box) return;
		const esc = frappe.utils.escape_html;
		const fmt = (v) => (typeof v === "number" ? v.toLocaleString() : esc(String(v)));
		const draw = (d) => {
			box.innerHTML = `
				<style>
					.rdn { padding: 4px 2px 8px; }
					.rdn-head { display:flex; align-items:baseline; gap:12px; margin-bottom:6px; }
					.rdn-head h4 { margin:0; font-size:15px; font-weight:600; }
					.rdn-head a { margin-left:auto; font-size:12px; }
					.rdn-group { margin: 10px 0 4px; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color: var(--text-muted); }
					.rdn-cards { display:grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap:10px; }
					.rdn-card { border:1px solid var(--border-color); border-radius:10px; padding:10px 12px; cursor:pointer; background: var(--card-bg); text-align:left; }
					.rdn-card:hover { border-color: var(--primary); }
					.rdn-card .v { font-size:22px; font-weight:600; line-height:1.2; }
					.rdn-card .v small { font-size:12px; color: var(--text-muted); font-weight:400; }
					.rdn-card .l { font-size:13px; font-weight:500; }
					.rdn-card .s { font-size:12px; color: var(--text-muted); }
					.rdn-card.alert .v { color: var(--orange-600, #c45a00); }
				</style>
				<div class="rdn">
					<div class="rdn-head"><h4>${__("Your library today")}</h4><span class="text-muted small">${__("as of {0}", [esc(d.as_of)])}</span><a href="#" class="rdn-refresh">${__("Refresh")}</a></div>
					${d.groups
						.map((g, gi) => `<div class="rdn-group">${esc(g.title)}</div><div class="rdn-cards">${g.cards
							.map((c, ci) => `<button type="button" class="rdn-card ${c.alert && c.value ? "alert" : ""}" data-g="${gi}" data-c="${ci}">
								<div class="v">${fmt(c.value)}${c.suffix ? `<small>${esc(c.suffix)}</small>` : ""}</div>
								<div class="l">${esc(c.label)}</div><div class="s">${esc(c.sub || "")}</div></button>`)
							.join("")}</div>`)
						.join("")}
				</div>`;
			box.querySelector(".rdn-refresh").onclick = (e) => {
				e.preventDefault();
				load(1);
			};
			box.querySelectorAll(".rdn-card").forEach((b) => {
				b.onclick = () => {
					const c = d.groups[b.dataset.g].cards[b.dataset.c];
					if (c.url) return window.open(c.url, c.url.startsWith("/") ? "_self" : "_blank");
					if (c.route) frappe.set_route(...c.route);
				};
			});
		};
		const load = (refresh) =>
			frappe.call({ method: "sok_resdesk.dashboard.numbers", args: { refresh: refresh || 0 } }).then((r) => r.message && draw(r.message));
		load(0);
	};

	window.rd_checklist = function (root) {
		const box = root.querySelector(".rd-checklist");
		if (!box) return;
		const esc = frappe.utils.escape_html;
		const draw = (d) => {
			if (d.hidden) {
				// a hidden guide leaves a one-line way back, so it can always be brought back
				box.innerHTML = `<div class="text-muted small" style="padding:4px 2px">${__("The getting-started guide is hidden.")}
					<a href="#" class="rdc-show">${__("Show the guide again")}</a></div>`;
				box.querySelector(".rdc-show").onclick = (e) => {
					e.preventDefault();
					frappe.call({ method: "sok_resdesk.guide.checklist_mark", args: { key: "", what: "show" } }).then((r) => draw(r.message));
				};
				return;
			}
			const n = d.steps.filter((s) => s.done || s.skipped).length;
			box.innerHTML = `
				<style>
					.rdc { padding: 4px 2px; }
					.rdc-head { display:flex; align-items:baseline; gap:12px; margin-bottom: 8px; }
					.rdc-head h4 { margin:0; font-size: 15px; font-weight: 600; }
					.rdc-head .rdc-hide { margin-left:auto; font-size:12px; }
					.rdc-bar { height:6px; background: var(--gray-200, #eee); border-radius:4px; overflow:hidden; margin-bottom:10px; }
					.rdc-bar div { height:100%; background: var(--primary, #2f6f5e); }
					.rdc-steps { list-style:none; margin:0; padding:0; display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:10px; }
					.rdc-step { border:1px solid var(--border-color); border-radius:8px; padding:10px 12px; display:flex; flex-direction:column; gap:6px; }
					.rdc-step.done { opacity:.65; }
					.rdc-title { font-weight:600; font-size:13px; display:flex; gap:8px; align-items:center; }
					.rdc-dot { width:18px; height:18px; border-radius:50%; border:1.5px solid var(--gray-400, #bbb); display:inline-flex; align-items:center; justify-content:center; font-size:11px; flex:none; }
					.rdc-step.done .rdc-dot { background: var(--green-500, #2e9e5b); border-color: var(--green-500, #2e9e5b); color:#fff; }
					.rdc-desc { font-size:12px; color: var(--text-muted); line-height:1.45; }
					.rdc-actions { display:flex; gap:6px; margin-top:auto; }
					.rdc-link { background:none; border:0; padding:0; color: var(--text-muted); font-size:12px; cursor:pointer; text-decoration: underline; }
				</style>
				<div class="rdc">
					<div class="rdc-head">
						<h4>${__("Get started with Research Desk")}</h4>
						<span class="text-muted small">${__("{0} of {1} done", [n, d.steps.length])}</span>
						<button class="rdc-link rdc-hide">${d.finished ? __("All done, hide this") : __("Hide checklist")}</button>
					</div>
					<div class="rdc-bar"><div style="width:${Math.round((n / d.steps.length) * 100)}%"></div></div>
					<ol class="rdc-steps">${d.steps
						.map(
							(s, i) => `<li class="rdc-step ${s.done || s.skipped ? "done" : ""}">
							<div class="rdc-title"><span class="rdc-dot">${s.done ? "✓" : s.skipped ? "–" : i + 1}</span>${esc(s.title)}</div>
							<div class="rdc-desc">${esc(s.description)}</div>
							<div class="rdc-actions">
								<button class="btn btn-xs ${s.done ? "btn-default" : "btn-primary"}" data-start="${s.key}">${esc(s.action.label)}</button>
								${s.done || s.skipped ? "" : `<button class="rdc-link" data-skip="${s.key}">${__("Skip")}</button>`}
							</div>
						</li>`
						)
						.join("")}</ol>
				</div>`;
			box.querySelector(".rdc-hide").onclick = () =>
				frappe.call({ method: "sok_resdesk.guide.checklist_mark", args: { key: "", what: "hide" } }).then((r) => draw(r.message));
			box.querySelectorAll("[data-skip]").forEach((b) => {
				b.onclick = () =>
					frappe
						.call({ method: "sok_resdesk.guide.checklist_mark", args: { key: b.dataset.skip, what: "skipped" } })
						.then((r) => draw(r.message));
			});
			box.querySelectorAll("[data-start]").forEach((b) => {
				b.onclick = () => start_step(d.steps.find((s) => s.key === b.dataset.start));
			});
		};
		frappe.call({ method: "sok_resdesk.guide.checklist" }).then((r) => draw(r.message));
	};
})();

