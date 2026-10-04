// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Portal Translations: every phrase readers see on the portal, with a column for each language
// the portal is offered in (Settings → Portal Languages). Type a translation and it is saved
// when you leave the box; download the spreadsheet to translate offline and upload it back
// (sok_resdesk/translations.py).

frappe.pages["resdesk-translations"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Portal Translations"), single_column: true });
	wrapper.resdesk_translations = new ResDeskTranslations(page);
};

frappe.pages["resdesk-translations"].on_page_show = function (wrapper) {
	wrapper.resdesk_translations && wrapper.resdesk_translations.refresh();
};

class ResDeskTranslations {
	constructor(page) {
		this.page = page;
		this.q = "";
		this.missing = 0;
		this.$body = $('<div class="rdt"></div>').appendTo(page.main);
		page.set_primary_action(__("Download spreadsheet"), () => {
			window.location.href = "/api/method/sok_resdesk.translations.download";
		}, "download");
		page.set_secondary_action(__("Upload spreadsheet"), () => this.upload(), "upload");
		page.add_menu_item(__("Portal Languages (Settings)"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("All translations (Frappe)"), () => frappe.set_route("List", "Translation"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/staff-guide#the-portal-in-other-languages") : frappe.set_route("resdesk-help", "staff-guide")
		);
		this.$body.on("input", ".rdt-search", frappe.utils.debounce((e) => {
			this.q = e.target.value.trim().toLowerCase();
			this.paint_rows();
		}, 250));
		this.$body.on("change", ".rdt-missing", (e) => {
			this.missing = e.target.checked ? 1 : 0;
			this.paint_rows();
		});
		this.$body.on("change", "textarea[data-lang]", (e) => this.save($(e.currentTarget)));
	}

	refresh() {
		frappe.call("sok_resdesk.translations.overview").then((r) => {
			this.data = r.message;
			this.render();
		});
	}

	render() {
		const esc = frappe.utils.escape_html;
		const langs = this.data.languages;
		if (!langs.length) {
			this.$body.html(`<div class="rdt-empty">
				<p>${__("The portal is offered only in English.")}</p>
				<p>${__("Add languages in Settings → Portal → Portal Languages (one code a line: kn for Kannada, hi for Hindi…); a language switch then appears at the top of the portal, and the phrases to translate are listed here.")}</p>
				<p><a class="btn btn-primary btn-sm" href="/app/rd-settings">${__("Open Settings")}</a></p></div>`);
			return;
		}
		const counts = langs
			.map((l) => `<span class="rdt-count${this.data.missing[l.code] ? " is-missing" : ""}">${esc(l.name)}: ${
				this.data.missing[l.code] ? __("{0} of {1} to translate", [this.data.missing[l.code], this.data.rows.length]) : __("all translated")
			}</span>`)
			.join("");
		this.$body.html(`
			<p class="rdt-intro text-muted">${__("Each phrase readers see on the portal, and what it reads as in each language. Type a translation and it is saved when you leave the box; empty a box to remove the library's translation. Keep {0}, {1}… where they are needed: they are filled in with numbers and names.")}</p>
			<div class="rdt-bar">
				<input type="search" class="form-control rdt-search" placeholder="${__("Find a phrase or a translation")}" value="${esc(this.q)}">
				<label class="rdt-check"><input type="checkbox" class="rdt-missing" ${this.missing ? "checked" : ""}> ${__("Only phrases still to translate")}</label>
				<div class="rdt-counts">${counts}</div>
			</div>
			<table class="table table-bordered rdt-table">
				<thead><tr><th>${__("Phrase (English)")}</th>${langs.map((l) => `<th lang="${esc(l.code)}">${esc(l.name)}</th>`).join("")}</tr></thead>
				<tbody></tbody>
			</table>
			<p class="rdt-shown text-muted"></p>`);
		this.paint_rows();
	}

	paint_rows() {
		const esc = frappe.utils.escape_html;
		const langs = this.data.languages;
		const rows = this.data.rows.filter((r) => {
			if (this.missing && langs.every((l) => r.t[l.code])) return false;
			if (!this.q) return true;
			return [r.source, r.where, ...langs.map((l) => r.t[l.code] || "")].some((x) => String(x).toLowerCase().includes(this.q));
		});
		const shown = rows.slice(0, 400);
		this.$body.find(".rdt-table tbody").html(
			shown
				.map(
					(r, n) => `<tr>
						<td><div class="rdt-source">${esc(r.source)}</div><div class="rdt-where text-muted small">${esc(r.where)}</div></td>
						${langs
							.map(
								(l) => `<td><textarea class="form-control rdt-input${r.t[l.code] ? "" : " is-missing"}" rows="${r.source.length > 90 ? 3 : 1}"
									lang="${esc(l.code)}" data-lang="${esc(l.code)}" data-row="${this.data.rows.indexOf(r)}"
									aria-label="${esc(__("{0} in {1}", [r.source.slice(0, 60), l.name]))}"
									title="${r.own[l.code] ? __("The library's translation") : r.t[l.code] ? __("Shipped with Research Desk or Frappe; type to change it") : ""}">${esc(r.t[l.code] || "")}</textarea></td>`
							)
							.join("")}
					</tr>`
				)
				.join("")
		);
		this.$body.find(".rdt-shown").text(
			rows.length > shown.length
				? __("Showing {0} of {1} phrases: find a phrase to see the rest.", [shown.length, rows.length])
				: __("{0} phrases", [rows.length])
		);
	}

	save($t) {
		const row = this.data.rows[Number($t.data("row"))];
		const lang = $t.data("lang");
		const text = $t.val().trim();
		frappe
			.call({ method: "sok_resdesk.translations.save", args: { lang, source: row.source, text } })
			.then((r) => {
				row.t[lang] = text;
				row.own[lang] = !!text;
				$t.toggleClass("is-missing", !text);
				const done = (r.message || {}).result;
				if (done && done !== "unchanged") frappe.show_alert({ message: text ? __("Saved") : __("Removed"), indicator: "green" }, 2);
			})
			.catch(() => $t.val(row.t[lang] || ""));
	}

	upload() {
		const d = new frappe.ui.Dialog({
			title: __("Upload translations"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p class="text-muted">${__("The spreadsheet from Download spreadsheet, filled in and saved as CSV (UTF-8). Each filled cell becomes the library's translation; empty cells change nothing.")}</p>`,
				},
				{ fieldname: "file", fieldtype: "HTML", options: '<input type="file" accept=".csv,text/csv" class="form-control rdt-file">' },
			],
			primary_action_label: __("Upload"),
			primary_action: () => {
				const file = d.$wrapper.find(".rdt-file")[0].files[0];
				if (!file) return frappe.msgprint(__("Choose the CSV file first."));
				const reader = new FileReader();
				reader.onload = () => {
					frappe.call({ method: "sok_resdesk.translations.upload", args: { content: reader.result }, freeze: true }).then((r) => {
						const m = r.message;
						d.hide();
						let msg = __("{0} added, {1} changed, {2} unchanged, {3} left out.", [m.added, m.changed, m.unchanged, m.skipped]);
						if (m.not_offered.length) msg += "<br>" + __("Not portal languages (left out): {0}", [m.not_offered.join(", ")]);
						if (m.problems.length) msg += "<br>" + m.problems.map(frappe.utils.escape_html).join("<br>");
						frappe.msgprint({ title: __("Translations uploaded"), message: msg, indicator: "green" });
						this.refresh();
					});
				};
				reader.readAsText(file, "utf-8");
			},
		});
		d.show();
	}
}

frappe.dom.set_style(`
.rdt-intro { max-width: 80ch; }
.rdt-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
.rdt-bar .rdt-search { max-width: 320px; }
.rdt-check { margin: 0; font-weight: normal; }
.rdt-counts { display: flex; gap: 12px; flex-wrap: wrap; margin-left: auto; }
.rdt-count.is-missing { color: var(--orange-600, #c05600); }
.rdt-table td { vertical-align: top; }
.rdt-table th:first-child { width: 40%; }
.rdt-source { white-space: pre-wrap; overflow-wrap: anywhere; }
.rdt-input.is-missing { border-color: var(--orange-300, #f6ad55); }
.rdt-empty { max-width: 70ch; padding: 24px 0; }
`);
