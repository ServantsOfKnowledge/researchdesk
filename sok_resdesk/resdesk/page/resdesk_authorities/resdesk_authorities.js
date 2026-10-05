// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Authorities: the catalogue's authors matched to Wikidata people (and VIAF), its subjects to
// Library of Congress Subject Headings. Candidates are found in the background; a cataloguer
// accepts one, chooses none, or searches again (sok_resdesk/authority.py).

frappe.pages["resdesk-authorities"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Authorities"), single_column: true });
	wrapper.resdesk_authorities = new ResDeskAuthorities(page);
};

frappe.pages["resdesk-authorities"].on_page_show = function (wrapper) {
	wrapper.resdesk_authorities && wrapper.resdesk_authorities.refresh();
};

const RDA_STATES = ["Proposed", "Not looked at", "Nothing found", "Confirmed", "No match"];

class ResDeskAuthorities {
	constructor(page) {
		this.page = page;
		this.kind = "creator";
		this.status = "Proposed";
		this.q = "";
		this.$body = $('<div class="rda"></div>').appendTo(page.main);
		page.set_primary_action(__("Find matches"), () => this.find(), "search");
		page.add_menu_item(__("Authors (all)"), () => frappe.set_route("List", "RD Creator"));
		page.add_menu_item(__("Subjects (all)"), () => frappe.set_route("List", "RD Subject"));
		page.add_menu_item(__("Settings → Authorities"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/staff-guide#authors-and-subjects") : frappe.set_route("resdesk-help", "staff-guide")
		);
		const on = (sel, fn) => this.$body.on("click", sel, (e) => (e.preventDefault(), fn($(e.currentTarget))));
		on("[data-kind]", ($b) => ((this.kind = $b.data("kind")), this.refresh()));
		on("[data-status]", ($b) => ((this.status = $b.data("status")), this.refresh()));
		on("[data-accept]", ($b) => this.accept($b.data("name"), $b.data("accept")));
		on("[data-reject]", ($b) => this.call("reject", { kind: this.kind, name: $b.data("reject") }));
		on("[data-undo]", ($b) => this.call("undo", { kind: this.kind, name: $b.data("undo") }));
		on("[data-again]", ($b) => this.again($b.data("again")));
		on("[data-give-refresh]", () =>
			frappe.call("sok_resdesk.contribute.refresh").then(() =>
				frappe.show_alert({ message: __("Asking Wikidata what it has; refresh this page in a minute."), indicator: "blue" })
			)
		);
		on("[data-give-mine]", () =>
			frappe.confirm(
				__("Send these edits to Wikidata under your own Wikimedia account? Wikidata's history will show them as yours."),
				() =>
					frappe.call("sok_resdesk.contribute.send_mine").then(() =>
						frappe.show_alert({ message: __("Sending in the background."), indicator: "blue" })
					)
			)
		);
		on("[data-give-send]", () => {
			const target = this.$body.find(".rda-target").val();
			frappe.confirm(__("Send these edits to Wikidata through {0}?", [frappe.utils.escape_html(target)]), () =>
				frappe.call({ method: "sok_resdesk.contribute.send", args: { target } }).then(() =>
					frappe.show_alert({ message: __("Sending in the background."), indicator: "blue" })
				)
			);
		});
		this.$body.on("input", ".rda-search", frappe.utils.debounce((e) => ((this.q = e.target.value.trim()), this.refresh()), 300));
	}

	call(method, args) {
		return frappe.call({ method: `sok_resdesk.authority.${method}`, args }).then((r) => {
			this.refresh();
			return r.message;
		});
	}

	refresh() {
		if (this.kind === "give") {
			return frappe.call("sok_resdesk.contribute.plan").then((r) => {
				this.give = r.message;
				this.render_give();
			});
		}
		frappe.call({ method: "sok_resdesk.authority.overview", args: { kind: this.kind, status: this.status, q: this.q } }).then((r) => {
			this.data = r.message;
			this.render();
		});
	}

	tabs() {
		return [
			["creator", __("Authors")],
			["subject", __("Subjects")],
			["give", __("Give back")],
		]
			.map(([k, l]) => `<button class="btn btn-sm ${k === this.kind ? "btn-primary" : "btn-default"}" data-kind="${k}">${l}</button>`)
			.join(" ");
	}

	render_give() {
		const esc = frappe.utils.escape_html;
		const g = this.give;
		const kinds = { label: __("Name added as a label"), alias: __("Name added as an alias"), author: __("Author linked on a book") };
		const rows = (g.edits || [])
			.map(
				(e) => `<tr><td><a href="https://www.wikidata.org/wiki/${esc(e.qid)}" target="_blank" rel="noopener">${esc(e.qid)}</a></td>
				<td>${esc(kinds[e.kind] || e.kind)}${e.lang ? ` (${esc(e.lang)})` : ""}</td>
				<td>${e.kind === "author" ? `<a href="https://www.wikidata.org/wiki/${esc(e.person)}" target="_blank" rel="noopener">${esc(e.person)}</a>, ${__("stated as")} ` : ""}<span${e.lang ? ` lang="${esc(e.lang)}"` : ""}>${esc(e.value)}</span></td></tr>`
			)
			.join("");
		const last = g.last_send
			? `<p class="small">${__("Last sent")}: ${esc(g.last_send.when)} · ${g.last_send.dry_run ? __("dry run: {0} edits on {1} items would be made", [g.last_send.edits, g.last_send.items]) : __("{0} edits on {1} items, {2} failed", [g.last_send.edits, g.last_send.items, g.last_send.failed])}</p>`
			: "";
		const targets = (g.targets || []).map((t) => `<option value="${esc(t.name)}">${esc(t.name)}${t.dry_run ? ` (${__("dry run")})` : ""}</option>`).join("");
		this.$body.html(`
			<p class="text-muted rda-intro">${__("What the library has learned while matching its authors, given back to Wikidata: people's names in the scripts of the library's books, and author links on the library's book items on Wikidata. Nothing already on Wikidata is changed or removed. Send it under your own Wikimedia account (connect it once under My Wikimedia Account), download the list as QuickStatements to review and run yourself, or send it through the library's Wikidata Push Target.")}</p>
			<div class="rda-bar">${this.tabs()}</div>
			<div class="rda-give">
				<p>${g.made_on ? __("Worked out {0} from {1} matched people and {2} books on Wikidata.", [frappe.datetime.comment_when(g.made_on), g.people, g.books]) : __("Not worked out yet.")}
					<button class="btn btn-xs btn-default" data-give-refresh>${__("Work it out again")}</button></p>
				<p><b>${g.counts.label}</b> ${__("names in a new language")} · <b>${g.counts.alias}</b> ${__("other names")} · <b>${g.counts.author}</b> ${__("author links")}</p>
				<div class="rda-acts">
					<a class="btn btn-sm btn-default" href="/api/method/sok_resdesk.contribute.quickstatements">${__("Download QuickStatements")}</a>
					${g.mine
						? `<button class="btn btn-sm btn-primary" data-give-mine>${__("Send as {0}", [esc(g.mine)])}</button>`
						: `<a class="btn btn-sm btn-default" href="/app/rd-wikimedia-account">${__("Connect my Wikimedia account to send as me")}</a>`}
					${targets ? `<select class="form-control input-sm rda-target" aria-label="${__("Wikidata Push Target")}">${targets}</select><button class="btn btn-sm btn-primary" data-give-send>${__("Send to Wikidata")}</button>` : `<span class="text-muted small">${__("To send directly, add a Wikidata Push Target (Research Desk → Metadata).")}</span>`}
				</div>
				${last}
				<h5>${__("Subjects for the Library of Congress")}</h5>
				<p class="small">${__("{0} subjects have no LCSH heading. Libraries in the SACO programme can propose new headings; the spreadsheet lists them with how many books use each and example titles.", [g.saco])}
					<a class="btn btn-xs btn-default" href="/api/method/sok_resdesk.contribute.saco">${__("Download for SACO")}</a></p>
				${rows ? `<table class="table table-bordered small"><thead><tr><th>${__("Wikidata item")}</th><th>${__("Edit")}</th><th>${__("Value")}</th></tr></thead><tbody>${rows}</tbody></table>` : ""}
			</div>`);
	}

	find() {
		const what = this.kind === "creator" ? __("authors") : __("subjects");
		frappe.prompt(
			{ fieldname: "limit", fieldtype: "Int", label: __("How many {0}", [what]), default: 200 },
			(v) =>
				frappe.call({ method: "sok_resdesk.authority.find", args: { kind: this.kind, limit: v.limit } }).then(() =>
					frappe.show_alert({ message: __("Looking up {0} {1} in the background (the ones with most books first).", [v.limit, what]), indicator: "blue" })
				),
			__("Find matches"),
			__("Start")
		);
	}

	accept(name, choice) {
		this.call("accept", { kind: this.kind, name, choice }).then((m) => {
			const same = (m && m.same_person) || [];
			if (!same.length) return frappe.show_alert({ message: __("Matched"), indicator: "green" });
			const esc = frappe.utils.escape_html;
			frappe.confirm(
				__("{0} is the same person as {1} in the catalogue. Put all their books under {0}?", [
					esc(name),
					same.map((s) => `<b>${esc(s.name)}</b>`).join(", "),
				]),
				() => Promise.all(same.map((s) => frappe.call({ method: "sok_resdesk.authority.merge", args: { name: s.name, into: name } }))).then(() => this.refresh())
			);
		});
	}

	again(name) {
		const label = this.kind === "creator" ? __("Name, or a Wikidata Q-number") : __("Words to search the subject headings for");
		frappe.prompt({ fieldname: "q", fieldtype: "Data", label, default: name }, (v) =>
			this.call("search_again", { kind: this.kind, name, q: v.q })
		, __("Search again"), __("Search"));
	}

	render() {
		const esc = frappe.utils.escape_html;
		const d = this.data;
		const creator = this.kind === "creator";
		const tabs = this.tabs();
		const states = RDA_STATES.map(
			(s) => `<button class="btn btn-xs ${s === this.status ? "btn-primary" : "btn-default"}" data-status="${esc(s)}">${esc(__(s))} <span class="badge">${d.counts[s] || 0}</span></button>`
		).join(" ");
		const link = (c) =>
			creator
				? `<a href="https://www.wikidata.org/wiki/${esc(c.id)}" target="_blank" rel="noopener">${esc(c.id)}</a>${c.viaf ? ` · <a href="https://viaf.org/viaf/${esc(c.viaf)}" target="_blank" rel="noopener">VIAF</a>` : ""}`
				: `<a href="${esc(c.uri || "")}" target="_blank" rel="noopener">${esc(c.id)}</a>`;
		const cand = (r, c) => `<li class="rda-cand">
			<div><b>${esc(c.label || c.id)}</b>${creator && (c.born || c.died) ? ` <span class="text-muted">(${c.born || "?"}–${c.died || ""})</span>` : ""}
				<span class="rda-score" title="${esc((c.reasons || []).join("; "))}">${Math.round((c.score || 0) * 100)}%</span></div>
			${c.description ? `<div class="small">${esc(c.description)}</div>` : ""}
			<div class="small text-muted">${link(c)}${c.reasons && c.reasons.length ? " · " + esc(c.reasons.join("; ")) : ""}</div>
			${r.match_status !== "Confirmed" ? `<button class="btn btn-xs btn-default" data-name="${esc(r.name)}" data-accept="${esc(c.id)}">${__("This one")}</button>` : ""}
		</li>`;
		const matched = (r) =>
			creator
				? r.wikidata_id
					? `<div class="rda-matched">✓ <a href="https://www.wikidata.org/wiki/${esc(r.wikidata_id)}" target="_blank" rel="noopener">${esc(r.wikidata_id)}</a>${r.viaf_id ? ` · VIAF ${esc(r.viaf_id)}` : ""}${r.born || r.died ? ` · ${r.born || "?"}–${r.died || ""}` : ""}${r.authority_description ? ` · ${esc(r.authority_description)}` : ""}</div>`
					: ""
				: r.lcsh_id
				? `<div class="rda-matched">✓ ${esc(r.lcsh_label)} (${esc(r.lcsh_id)})</div>`
				: "";
		const rows = d.rows
			.map(
				(r) => `<div class="rda-row">
				<div class="rda-name">
					<a href="/app/${creator ? "rd-creator" : "rd-subject"}/${encodeURIComponent(r.name)}"><b>${esc(r.name)}</b></a>
					${creator && r.alt_name ? `<span class="text-muted"> · ${esc(r.alt_name)}</span>` : ""}
					<div class="small text-muted">${__("{0} books", [r.books])}${r.matched_by ? ` · ${esc(r.match_status)} ${__("by")} ${esc(r.matched_by)}` : ""}</div>
					${matched(r)}
					<div class="rda-acts">
						${r.match_status === "Confirmed" || r.match_status === "No match"
							? `<button class="btn btn-xs btn-default" data-undo="${esc(r.name)}">${__("Undo")}</button>`
							: `<button class="btn btn-xs btn-default" data-reject="${esc(r.name)}">${__("None of these")}</button>`}
						<button class="btn btn-xs btn-default" data-again="${esc(r.name)}">${__("Search again")}</button>
					</div>
				</div>
				<ul class="rda-cands">${(r.candidates || []).map((c) => cand(r, c)).join("") || `<li class="text-muted">${__("No candidates.")}</li>`}</ul>
			</div>`
			)
			.join("");
		this.$body.html(`
			<p class="text-muted rda-intro">${creator
				? __("Authors matched to a person on Wikidata (and through it VIAF) are gathered under one name on the portal, link to a page about the person, and carry the identifiers in MARC, JSON-LD and DOIs. Candidates are scored by name, whether they are a person, and whether their dates fit the books.")
				: __("Subjects matched to a Library of Congress Subject Heading go to Koha and other library systems as controlled headings (MARC 650) with their identifier.")}</p>
			<div class="rda-bar">${tabs}<input type="search" class="form-control rda-search" placeholder="${__("Find a name")}" value="${esc(this.q)}"></div>
			<div class="rda-states">${states}</div>
			<div class="rda-rows">${rows || `<p class="text-muted">${__("Nothing here.")}${this.status === "Not looked at" ? "" : " " + __("Use Find matches to look up names not looked at yet.")}</p>`}</div>`);
	}
}

frappe.dom.set_style(`
.rda-intro { max-width: 90ch; }
.rda-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 10px 0; }
.rda-bar .rda-search { max-width: 280px; margin-left: auto; }
.rda-states { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.rda-row { display: grid; grid-template-columns: minmax(200px, 1fr) 2fr; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--border-color); }
.rda-acts { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.rda-cands { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.rda-cand { border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; }
.rda-score { float: right; font-weight: 600; }
.rda-matched { margin-top: 6px; }
@media (max-width: 800px) { .rda-row { grid-template-columns: 1fr; } }
`);
