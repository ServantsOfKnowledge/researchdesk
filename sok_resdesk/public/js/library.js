// Research Desk search page. Vanilla JS, no build step.
(function () {
	const $ = (sel) => document.querySelector(sel);
	const FACET_LABELS = {
		curated: "Collection",
		item_type: "Type",
		language_label: "Language",
		decade: "Decade",
		subjects: "Subject",
		creators: "Author",
		collections: "Source collection",
	};
	// ids shown as names (curated collections); filters fixed by the page (a collection page)
	const LABELS = window.RD_LABELS || {};
	const label = (field, value) => (LABELS[field] && LABELS[field][value]) || value;
	const rootData = () => (document.getElementById("rd-library") || {}).dataset || {};
	let FIXED = {};
	try {
		FIXED = JSON.parse(rootData().fixed || "{}");
	} catch (e) {
		FIXED = {};
	}
	const FACET_FIELDS = Object.keys(FACET_LABELS);
	const state = { q: "", mode: "books", page: 1, sort: "", filters: {} };

	function esc(s) {
		return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	}
	// Meilisearch returns highlighted HTML; allow only <mark>.
	function safeMarked(s) {
		return esc(s).replace(/&lt;mark&gt;/g, "<mark>").replace(/&lt;\/mark&gt;/g, "</mark>");
	}

	// ---- URL <-> state -----------------------------------------------------------
	function fromUrl() {
		const p = new URLSearchParams(location.search);
		state.q = p.get("q") || "";
		state.mode = p.get("mode") === "pages" ? "pages" : "books";
		state.page = parseInt(p.get("page") || "1", 10);
		state.sort = p.get("sort") || "";
		state.filters = {};
		FACET_FIELDS.forEach((f) => {
			const v = p.getAll(f);
			if (v.length) state.filters[f] = v;
		});
		["year_from", "year_to"].forEach((f) => p.get(f) && (state.filters[f] = p.get(f)));
	}
	function toUrl() {
		const p = new URLSearchParams();
		if (state.q) p.set("q", state.q);
		if (state.mode !== "books") p.set("mode", state.mode);
		if (state.page > 1) p.set("page", state.page);
		if (state.sort) p.set("sort", state.sort);
		Object.entries(state.filters).forEach(([k, v]) => (Array.isArray(v) ? v.forEach((x) => p.append(k, x)) : p.set(k, v)));
		history.replaceState(null, "", `${location.pathname}${p.toString() ? "?" + p : ""}`);
	}
	function syncForm() {
		$("#rd-q").value = state.q;
		document.querySelectorAll('input[name="rd-mode"]').forEach((r) => (r.checked = r.value === state.mode));
		$("#rd-sort").value = state.sort;
		$("#rd-sort").disabled = state.mode === "pages";
		$("#rd-year-from").value = state.filters.year_from || "";
		$("#rd-year-to").value = state.filters.year_to || "";
	}

	function allFilters() {
		const out = { ...state.filters };
		Object.entries(FIXED).forEach(([k, v]) => (out[k] = [...new Set([...(out[k] || []), ...v])]));
		return out;
	}

	// ---- API --------------------------------------------------------------------
	async function run() {
		toUrl();
		syncForm();
		$("#rd-hits").innerHTML = '<li class="rd-muted">Searching…</li>';
		const params = new URLSearchParams({
			q: state.q,
			mode: state.mode,
			page: state.page,
			per_page: 20,
			sort: state.sort,
			filters: JSON.stringify(allFilters()),
		});
		try {
			const res = await fetch(`/api/method/sok_resdesk.api.search?${params}`, { headers: { Accept: "application/json" } });
			const body = await res.json();
			if (!res.ok) throw new Error(body._server_messages || body.exception || res.statusText);
			render(body.message);
			if (state.q && state.page === 1 && window.rdTrack)
				rdTrack("Search", { mode: state.mode || "books", results: (body.message || {}).total || 0 });
		} catch (e) {
			$("#rd-hits").innerHTML = `<li class="rd-error">Search is unavailable right now. ${esc(e.message).slice(0, 200)}</li>`;
		}
	}

	// ---- rendering ------------------------------------------------------------------
	function render(data) {
		lastTotal = data.total || 0;
		paintStaffBar();
		if (data.login_needed) {
			const root = $("#rd-library").dataset;
			$("#rd-summary").textContent = "";
			$("#rd-facet-lists").innerHTML = "";
			$("#rd-pager").innerHTML = "";
			$("#rd-hits").innerHTML = `<li class="rd-empty"><a href="${esc(root.login)}">Log in</a> to search inside the text of the books.${
				root.signup === "1" ? ' No account? <a href="/login#signup">Create one</a>.' : ""}</li>`;
			return;
		}
		const noun = state.mode === "pages" ? "matching pages" : "books";
		$("#rd-summary").textContent = `${(data.total || 0).toLocaleString()}${data.total_capped ? "+" : ""} ${noun}${data.took_ms != null ? ` · ${data.took_ms} ms` : ""}`;
		// a search in Latin letters also found these spellings (search.expand_query)
		const also = (data.also || []).map((a) => `<b lang="${a.script === "Devanagari" ? "hi" : ""}">${esc(a.q)}</b>`);
		$("#rd-also").innerHTML = also.length ? `Also searched: ${also.join(", ")}` : "";
		$("#rd-also").hidden = !also.length;
		renderChips();
		renderFacets(data.facets || {});
		const hits = data.hits || [];
		if (!hits.length) {
			$("#rd-hits").innerHTML = `<li class="rd-empty">No results. Try fewer words, another spelling, or remove a filter.</li>`;
		} else {
			$("#rd-hits").innerHTML = hits.map(state.mode === "pages" ? pageHit : bookHit).join("");
		}
		renderPager(data.page || 1, data.total_pages || 0);
		markBasket();
	}

	function bookHit(h) {
		const meta = [h.year || "n.d.", h.language, h.page_count ? `${h.page_count} pp.` : ""].filter(Boolean).join(" · ");
		return `<li class="rd-hit">
			<a href="${h.url}" class="rd-hit__thumb">${h.thumbnail ? `<img src="${esc(h.thumbnail)}" alt="" loading="lazy">` : ""}</a>
			<div class="rd-hit__body">
				<h3><a href="${h.url}">${safeMarked(h.title_html)}</a></h3>
				${h.alt_title && h.alt_title !== h.title ? `<div class="rd-muted">${esc(h.alt_title)}</div>` : ""}
				<div class="rd-hit__creators">${(h.creators || []).map(esc).join("; ")}</div>
				<div class="rd-muted">${esc(meta)}${h.has_fulltext ? ' · <span class="rd-badge">full text</span>' : ""}${lockBadge(h)}</div>
				${h.snippet ? `<p class="rd-snippet">${safeMarked(h.snippet)}</p>` : ""}
			</div>
			<button class="rd-save" data-id="${esc(h.item_id)}" type="button" title="Add to my list" aria-label="Add to my list">＋</button>
		</li>`;
	}

	function pageHit(h) {
		const label = String(h.page_label || "").startsWith("§")
			? esc(h.page_label)
			: h.page_label ? `p. ${esc(h.page_label)}` : `leaf ${h.leaf}`;
		const url = `${h.url}&q=${encodeURIComponent(state.q)}#rd-reader`;
		return `<li class="rd-hit rd-hit--page">
			<div class="rd-hit__body">
				<h3><a href="${url}">${esc(h.title)}</a> <span class="rd-muted">· ${label}</span>${lockBadge(h)}</h3>
				<div class="rd-muted">${(h.creators || []).map(esc).join("; ")}${h.year ? " · " + h.year : ""}</div>
				<p class="rd-snippet">${safeMarked(h.snippet)}</p>
			</div>
			<button class="rd-save" data-id="${esc(h.item_id)}" type="button" title="Add book to my list" aria-label="Add book to my list">＋</button>
		</li>`;
	}

	function lockBadge(h) {
		if (!h.visibility || h.visibility === "Public") return "";
		const text = h.visibility === "Login to find" ? "members only" : "login to read";
		return ` · <span class="rd-badge rd-badge--members" title="${esc(h.visibility)}">🔒 ${text}</span>`;
	}

	// ---- staff: change visibility of everything matching the current search --------------
	let lastTotal = 0;
	function paintStaffBar() {
		const bar = $("#rd-staffbar");
		if (!bar) return;
		bar.hidden = !lastTotal;
		if ($("#rd-staffbar-coll")) $("#rd-staffbar-coll").hidden = !lastTotal;
		$("#rd-staff-count").textContent = lastTotal.toLocaleString();
		$("#rd-staff-msg").textContent = state.mode === "pages" ? "(books with a matching page)" : "";
	}
	async function applyStaffBar(e) {
		e.preventDefault();
		const vis = $("#rd-staff-vis").value;
		if (!confirm(`Set ${lastTotal.toLocaleString()} ${state.mode === "pages" ? "matching pages' books" : "books"} to “${vis}”?`)) return;
		$("#rd-staff-msg").textContent = "Working…";
		const body = new URLSearchParams({
			visibility: vis,
			search: JSON.stringify({ q: state.q, mode: state.mode, filters: allFilters() }),
		});
		try {
			const res = await fetch("/api/method/sok_resdesk.access.bulk_set_visibility", {
				method: "POST",
				headers: { Accept: "application/json", "X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "" },
				body,
			});
			const out = await res.json();
			if (!res.ok) throw new Error(out.exception || res.statusText);
			$("#rd-staff-msg").textContent = out.message.message;
			if (!out.message.queued) setTimeout(run, 800);
		} catch (err) {
			$("#rd-staff-msg").textContent = `Could not change: ${String(err.message).slice(0, 160)}`;
		}
	}

	async function addToCollection(e) {
		e.preventDefault();
		let coll = $("#rd-staff-coll").value;
		const csrf = (window.frappe && frappe.csrf_token) || "";
		const post = async (method, params) => {
			const res = await fetch(`/api/method/${method}`, {
				method: "POST",
				headers: { Accept: "application/json", "X-Frappe-CSRF-Token": csrf },
				body: new URLSearchParams(params),
			});
			const out = await res.json();
			if (!res.ok) throw new Error(out.exception || res.statusText);
			return out.message;
		};
		try {
			if (coll === "__new__") {
				const title = prompt("Name of the new collection:");
				if (!title) return;
				coll = await post("sok_resdesk.curation.create", { title });
			}
			const action = $("#rd-staff-coll-action").value;
			const verb = action === "add" ? "Add" : "Remove";
			if (!confirm(`${verb} ${lastTotal.toLocaleString()} ${state.mode === "pages" ? "matching pages' books" : "books"} ${action === "add" ? "to" : "from"} “${label("curated", coll)}”?`)) return;
			$("#rd-staff-msg").textContent = "Working…";
			const out = await post("sok_resdesk.curation.bulk", {
				action,
				collection: coll,
				search: JSON.stringify({ q: state.q, mode: state.mode, filters: allFilters() }),
			});
			$("#rd-staff-msg").textContent = out.message;
		} catch (err) {
			$("#rd-staff-msg").textContent = `Could not change: ${String(err.message).slice(0, 160)}`;
		}
	}

	function renderFacets(facets) {
		const html = FACET_FIELDS.map((field) => {
			const values = Object.entries(facets[field] || {}).filter(([v]) => !(FIXED[field] || []).includes(v));
			if (!values.length) return "";
			const selected = state.filters[field] || [];
			if (field === "decade") values.sort((a, b) => a[0].localeCompare(b[0]));
			const shown = values.slice(0, 12);
			const rows = shown
				.map(
					([v, n]) => `<li><label><input type="checkbox" data-field="${field}" value="${esc(v)}" ${selected.includes(v) ? "checked" : ""}>
						<span>${esc(label(field, v))}</span> <span class="rd-muted">${n}</span></label></li>`
				)
				.join("");
			return `<div class="rd-facet"><h3>${FACET_LABELS[field]}</h3><ul>${rows}</ul></div>`;
		}).join("");
		$("#rd-facet-lists").innerHTML = html;
	}

	function renderChips() {
		const chips = [];
		Object.entries(state.filters).forEach(([k, v]) =>
			(Array.isArray(v) ? v : [v]).forEach((x) =>
				chips.push(`<button class="rd-chip is-active" data-field="${k}" data-value="${esc(x)}" type="button">${esc(label(k, x))} ✕</button>`)
			)
		);
		$("#rd-active-filters").innerHTML = chips.join("");
	}

	function renderPager(page, total) {
		if (total <= 1) return ($("#rd-pager").innerHTML = "");
		const btn = (p, label, dis) => `<button class="rd-btn" data-page="${p}" ${dis ? "disabled" : ""} type="button">${label}</button>`;
		$("#rd-pager").innerHTML = `${btn(page - 1, "← Previous", page <= 1)} <span class="rd-muted">Page ${page} of ${total}</span> ${btn(page + 1, "Next →", page >= total)}`;
	}

	function markBasket() {
		document.querySelectorAll(".rd-save").forEach((b) => {
			const on = RDBasket.has(b.dataset.id);
			b.classList.toggle("is-saved", on);
			b.textContent = on ? "✓" : "＋";
		});
		$("#rd-basket-count").textContent = RDBasket.ids().length;
	}

	// ---- events -----------------------------------------------------------------
	function bind() {
		$("#rd-search-form").addEventListener("submit", (e) => {
			e.preventDefault();
			state.q = $("#rd-q").value.trim();
			state.page = 1;
			run();
		});
		document.querySelectorAll('input[name="rd-mode"]').forEach((r) =>
			r.addEventListener("change", () => {
				state.mode = r.value;
				state.page = 1;
				run();
			})
		);
		$("#rd-sort").addEventListener("change", (e) => {
			state.sort = e.target.value;
			state.page = 1;
			run();
		});
		["year-from", "year-to"].forEach((id) =>
			$(`#rd-${id}`).addEventListener("change", (e) => {
				const key = id.replace("-", "_");
				e.target.value ? (state.filters[key] = e.target.value) : delete state.filters[key];
				state.page = 1;
				run();
			})
		);
		$("#rd-facet-lists").addEventListener("change", (e) => {
			const cb = e.target.closest("input[type=checkbox]");
			if (!cb) return;
			const list = new Set(state.filters[cb.dataset.field] || []);
			cb.checked ? list.add(cb.value) : list.delete(cb.value);
			list.size ? (state.filters[cb.dataset.field] = [...list]) : delete state.filters[cb.dataset.field];
			state.page = 1;
			run();
		});
		$("#rd-active-filters").addEventListener("click", (e) => {
			const chip = e.target.closest(".rd-chip");
			if (!chip) return;
			const { field, value } = chip.dataset;
			const v = state.filters[field];
			if (Array.isArray(v)) {
				state.filters[field] = v.filter((x) => x !== value);
				if (!state.filters[field].length) delete state.filters[field];
			} else delete state.filters[field];
			state.page = 1;
			run();
		});
		$("#rd-pager").addEventListener("click", (e) => {
			const b = e.target.closest("[data-page]");
			if (!b) return;
			state.page = parseInt(b.dataset.page, 10);
			run();
			window.scrollTo({ top: 0, behavior: "smooth" });
		});
		$("#rd-hits").addEventListener("click", (e) => {
			const b = e.target.closest(".rd-save");
			if (!b) return;
			RDBasket.toggle(b.dataset.id);
		});
		document.addEventListener("rd-basket-change", markBasket);
		if ($("#rd-staffbar")) $("#rd-staffbar").addEventListener("submit", applyStaffBar);
		if ($("#rd-staffbar-coll")) $("#rd-staffbar-coll").addEventListener("submit", addToCollection);

		// basket menu
		$("#rd-basket-btn").addEventListener("click", () => ($("#rd-basket-menu").hidden = !$("#rd-basket-menu").hidden));
		document.addEventListener("click", (e) => {
			if (!e.target.closest("#rd-basket")) $("#rd-basket-menu").hidden = true;
		});
		$("#rd-basket-menu").addEventListener("click", async (e) => {
			const a = e.target.closest("a");
			if (!a) return;
			e.preventDefault();
			if (!RDBasket.ids().length && a.dataset.action !== "clear") return alertMsg("Your list is empty. Use ＋ on a result to add books.");
			if (a.dataset.fmt) window.location = RDBasket.exportUrl(a.dataset.fmt);
			if (a.dataset.action === "clear") RDBasket.clear();
			if (a.dataset.action === "share") {
				try {
					await navigator.clipboard.writeText(RDBasket.shareUrl());
					alertMsg("Share link copied. Anyone opening it gets these books in their list.");
				} catch (err) {
					prompt("Copy this link:", RDBasket.shareUrl());
				}
			}
		});
	}

	function alertMsg(text) {
		if (window.frappe && frappe.show_alert) frappe.show_alert({ message: text, indicator: "blue" });
		else $("#rd-summary").textContent = text;
	}

	document.addEventListener("DOMContentLoaded", () => {
		fromUrl();
		bind();
		run();
	});
})();
