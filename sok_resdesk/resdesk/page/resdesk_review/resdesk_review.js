// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Review Queue: books whose records need a cataloguer's eye, most important questions first.
// Correct the title, year or language right here (kept through re-ingest), open the book for
// anything else, or answer "This is right" (sok_resdesk/review.py).

frappe.pages["resdesk-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Review Queue"), single_column: true });
	wrapper.resdesk_review = new ResDeskReview(page);
};

frappe.pages["resdesk-review"].on_page_show = function (wrapper) {
	wrapper.resdesk_review && wrapper.resdesk_review.refresh();
};

class ResDeskReview {
	constructor(page) {
		this.page = page;
		this.check = "";
		this.q = "";
		this.start = 0;
		this.$body = $('<div class="rdr"></div>').appendTo(page.main);
		page.set_primary_action(__("Scan now"), () =>
			frappe.call("sok_resdesk.review.scan_now").then(() =>
				frappe.show_alert({ message: __("Checking every book in the background; this page fills as it goes."), indicator: "blue" })
			), "refresh");
		page.add_menu_item(__("All questions (list)"), () => frappe.set_route("List", "RD Review Flag"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/staff-guide#the-review-queue") : frappe.set_route("resdesk-help", "staff-guide")
		);
		const on = (sel, fn) => this.$body.on("click", sel, (e) => (e.preventDefault(), fn($(e.currentTarget))));
		on("[data-check]", ($b) => ((this.check = $b.data("check") === this.check ? "" : $b.data("check")), (this.start = 0), this.refresh()));
		on("[data-ignore]", ($b) => this.call("ignore", { name: $b.data("ignore") }));
		on("[data-hide]", ($b) =>
			frappe.confirm(__("Take this copy off the portal? It stays in the Desk, and can be published again."), () =>
				this.call("hide_duplicate", { item: $b.data("hide") })
			)
		);
		on("[data-save]", ($b) => this.save($b.closest(".rdr-book")));
		on("[data-more]", ($b) => ((this.start += 25), this.refresh()));
		on("[data-less]", ($b) => ((this.start = Math.max(0, this.start - 25)), this.refresh()));
		this.$body.on("input", ".rdr-search", frappe.utils.debounce((e) => ((this.q = e.target.value.trim()), (this.start = 0), this.refresh()), 300));
		this.$body.on("keydown", ".rdr-edit input", (e) => e.key === "Enter" && (e.preventDefault(), this.save($(e.target).closest(".rdr-book"))));
	}

	call(method, args) {
		return frappe.call({ method: `sok_resdesk.review.${method}`, args }).then(() => {
			frappe.show_alert({ message: __("Done"), indicator: "green" }, 2);
			this.refresh();
		});
	}

	save($book) {
		const values = {};
		$book.find("[data-field]").each((_, el) => {
			if (el.value !== el.dataset.was) values[el.dataset.field] = el.value;
		});
		if (!Object.keys(values).length) return frappe.show_alert({ message: __("Nothing changed"), indicator: "orange" }, 2);
		this.call("save", { item: $book.data("item"), values: JSON.stringify(values) });
	}

	refresh() {
		frappe.call({ method: "sok_resdesk.review.overview", args: { check: this.check, q: this.q, start: this.start } }).then((r) => {
			this.data = r.message;
			this.render();
		});
	}

	render() {
		const esc = frappe.utils.escape_html;
		const d = this.data;
		const chips = Object.keys(d.counts)
			.map(
				(c) => `<button class="btn btn-xs ${c === this.check ? "btn-primary" : "btn-default"}" data-check="${c}">${esc(d.labels[c])} <span class="badge">${d.counts[c]}</span></button>`
			)
			.join(" ");
		const langs = d.languages.map((l) => `<option value="${esc(l.code)}">${esc(l.label)} (${esc(l.code)})</option>`).join("");
		const flag = (b, f) => {
			let extra = "";
			if (f.check === "duplicate") {
				extra = `<div class="small">${(f.others || [])
					.map((o) => `<a href="/app/rd-item/${encodeURIComponent(o.name)}">${esc(o.title || o.name)}</a>${o.year ? ` (${o.year})` : ""}${o.published ? "" : ` <span class="text-muted">${__("not on the portal")}</span>`}`)
					.join(" · ")}</div>
					<button class="btn btn-xs btn-default" data-hide="${esc(b.item_id)}">${__("Hide this copy")}</button>`;
			}
			return `<li class="rdr-flag rdr-w${f.weight}"><b>${esc(__(f.label))}</b>${f.detail && f.check !== "duplicate" ? `: <span>${esc(f.detail)}</span>` : ""}
				${extra}
				<button class="btn btn-xs btn-default" data-ignore="${esc(f.name)}" title="${__("The record is right: don't ask again")}">${f.check === "duplicate" ? __("Not a duplicate") : __("This is right")}</button></li>`;
		};
		const book = (b) => `<div class="rdr-book" data-item="${esc(b.item_id)}">
			<div class="rdr-head">
				<a href="/app/rd-item/${encodeURIComponent(b.item_id)}"><b>${esc(b.title || b.item_id)}</b></a>
				<span class="text-muted small"> · ${esc(b.item_id)} · ${esc((b.creators || []).join("; ") || __("no author"))} · <a href="/library/item/${encodeURIComponent(b.item_id)}" target="_blank">${__("on the portal")}</a></span>
			</div>
			<ul class="rdr-flags">${b.flags.map((f) => flag(b, f)).join("")}</ul>
			<div class="rdr-edit">
				<label>${__("Title")}<input class="form-control input-xs" data-field="title" data-was="${esc(b.title || "")}" value="${esc(b.title || "")}"></label>
				<label>${__("Year")}<input class="form-control input-xs" type="number" min="1000" max="2100" data-field="year" data-was="${esc(b.year || "")}" value="${esc(b.year || "")}"></label>
				<label>${__("Language")}<input class="form-control input-xs" list="rdr-langs" data-field="language" data-was="${esc(b.language || "")}" value="${esc(b.language || "")}"></label>
				<button class="btn btn-xs btn-primary" data-save>${__("Save")}</button>
			</div>
		</div>`;
		this.$body.html(`
			<p class="text-muted rdr-intro">${__("Books whose records need a person's eye, the most important questions first. Correct the title, year or language here (your edits are kept through re-ingest), open the book for anything else, or answer \"This is right\" so it isn't asked again. Each night every book is checked again; a corrected record leaves the queue at once.")}
				${d.last_scan ? `<br>${__("Last check")}: ${frappe.datetime.comment_when(d.last_scan)}` : ` <b>${__("Not checked yet: use Scan now.")}</b>`}</p>
			<div class="rdr-bar"><div class="rdr-chips">${chips}</div><input type="search" class="form-control rdr-search" placeholder="${__("Find a title or identifier")}" value="${esc(this.q)}"></div>
			<datalist id="rdr-langs">${langs}</datalist>
			<div class="rdr-books">${d.rows.map(book).join("") || `<p class="text-muted">${__("Nothing to review here.")}</p>`}</div>
			<div class="rdr-pager">${this.start ? `<button class="btn btn-xs btn-default" data-less>${__("← Previous")}</button>` : ""}
				${d.rows.length === 25 ? `<button class="btn btn-xs btn-default" data-more>${__("Next →")}</button>` : ""}</div>`);
	}
}

frappe.dom.set_style(`
.rdr-intro { max-width: 90ch; }
.rdr-bar { display: flex; gap: 10px; align-items: flex-start; flex-wrap: wrap; margin: 10px 0 14px; }
.rdr-chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.rdr-bar .rdr-search { max-width: 260px; }
.rdr-book { border-bottom: 1px solid var(--border-color); padding: 12px 0; }
.rdr-flags { margin: 6px 0; padding-left: 18px; }
.rdr-flag { margin: 4px 0; }
.rdr-flag .btn { margin-left: 6px; }
.rdr-w1 b { color: #b42318; }
.rdr-edit { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.rdr-edit label { display: flex; flex-direction: column; font-size: 12px; margin: 0; }
.rdr-edit label:first-child { flex: 1; min-width: 240px; }
.rdr-pager { display: flex; gap: 8px; margin-top: 12px; }
`);
