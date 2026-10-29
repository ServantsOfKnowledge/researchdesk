// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Circulation Desk: scan a member's card, then the books (lend) or the books alone (return). A barcode
// scanner types the code and presses Enter, so every box works with one.

frappe.pages["resdesk-circulation"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Circulation Desk"), single_column: true });
	wrapper.resdesk_circulation = new RDCirculation(page);
};

frappe.pages["resdesk-circulation"].on_page_show = function (wrapper) {
	if (wrapper.resdesk_circulation) wrapper.resdesk_circulation.lists();
};

class RDCirculation {
	constructor(page) {
		this.page = page;
		this.patron = null;
		const e = frappe.utils.escape_html;
		this.e = e;
		this.$ = $(`<div class="rdc">
			<p id="rdc-msg" class="rdc-msg" role="status" aria-live="polite" tabindex="-1"></p>
			<div class="row">
				<div class="col-md-6"><label for="rdc-member"><b>${__("Member")}</b> <span class="text-muted">${__("scan the card, or type a number or name")}</span></label>
					<input id="rdc-member" class="form-control input-sm" autocomplete="off" autofocus></div>
				<div class="col-md-6"><label for="rdc-return"><b>${__("Return a book")}</b> <span class="text-muted">${__("scan its barcode")}</span></label>
					<input id="rdc-return" class="form-control input-sm" autocomplete="off"></div>
			</div>
			<div id="rdc-choices" class="rdc-block"></div>
			<div id="rdc-patron" class="rdc-block"></div>
			<div class="row rdc-block"><div class="col-md-6" id="rdc-overdue"></div><div class="col-md-6" id="rdc-shelf"></div></div>
		</div>`).appendTo(page.main);
		this.$msg = this.$.find("#rdc-msg");
		page.set_secondary_action(__("Refresh"), () => this.lists(), "refresh");
		page.add_menu_item(__("New Member"), () => frappe.new_doc("RD Patron"));
		page.add_menu_item(__("Help for this screen"), () => (window.rd_open_help ? window.rd_open_help("/app/resdesk-help/lending#the-circulation-desk") : frappe.set_route("resdesk-help", "lending")));
		const enter = (sel, fn) => this.$.on("keydown", sel, (ev) => { if (ev.key === "Enter") { ev.preventDefault(); fn($(ev.currentTarget)); } });
		enter("#rdc-member", ($i) => this.find($i.val()));
		enter("#rdc-return", ($i) => this.checkin($i));
		enter("#rdc-lend", ($i) => this.checkout($i));
		this.$.on("click", "[data-pick]", (ev) => this.show($(ev.currentTarget).data("pick")));
		this.$.on("click", "[data-renew]", (ev) => this.act("renew", { loan: $(ev.currentTarget).data("renew") }));
		this.$.on("click", "[data-lost]", (ev) => frappe.confirm(__("Mark this book lost? The copy's price becomes a fine."), () => this.act("mark_lost", { loan: $(ev.currentTarget).data("lost") })));
		this.$.on("click", "[data-pay]", (ev) => this.act("settle_fine", { fine: $(ev.currentTarget).data("pay") }));
		this.$.on("click", "[data-waive]", (ev) => this.act("settle_fine", { fine: $(ev.currentTarget).data("waive"), waive: 1 }));
		this.$.on("click", "[data-cancel-hold]", (ev) => this.act("cancel_hold_staff", { hold: $(ev.currentTarget).data("cancel-hold") }));
		this.$.on("click", "[data-member]", (ev) => this.show($(ev.currentTarget).data("member")));
		this.lists();
	}

	say(text, ok = true) {
		this.$msg.text(text).css("color", ok ? "var(--green-600, #2f7d32)" : "var(--red-600, #b3261e)").focus();
	}

	call(method, args, done) {
		return frappe.call({ method: "sok_resdesk.lending." + method, args, freeze: false, error: (r) => this.say(this.why(r), false) }).then((r) => r && r.message && done && done(r.message));
	}

	why(r) {
		try { return JSON.parse(JSON.parse(r._server_messages || "[]")[0]).message.replace(/<[^>]+>/g, ""); } catch (x) { return __("That did not work."); }
	}

	find(q) {
		this.call("find_patron", { query: q }, (m) => {
			if (m.snapshot) return this.render(m.snapshot);
			const e = this.e;
			this.$.find("#rdc-patron").html("");
			this.$.find("#rdc-choices").html(m.choices.length
				? `<p>${__("Which member?")}</p>` + m.choices.map((c) => `<button class="btn btn-default btn-sm" data-pick="${e(c.name)}">${e(c.full_name)} · ${e(c.name)} · ${e(c.status)}</button> `).join("")
				: `<p class="text-muted">${__("No member found.")} <a href="/app/rd-patron/new">${__("Add a member")}</a></p>`);
		});
	}

	show(name) { this.call("desk_snapshot", { patron: name }, (m) => this.render(m)); }

	render(s) {
		const e = this.e, p = s.patron, cur = s.currency;
		this.patron = p.name;
		this.$.find("#rdc-choices").html("");
		this.$.find("#rdc-member").val("");
		const loans = s.loans.map((l) => `<tr><td>${e(l.title)}<br><small class="text-muted">${e(l.copy)}</small></td><td class="${l.overdue ? "text-danger" : ""}">${e(l.due_on)}${l.overdue ? " · " + __("overdue") : ""}</td><td class="text-right"><button class="btn btn-xs btn-default" data-renew="${e(l.name)}">${__("Renew")}</button> <button class="btn btn-xs btn-default" data-lost="${e(l.name)}">${__("Lost")}</button></td></tr>`).join("");
		const holds = s.holds.map((h) => `<tr><td>${e(h.title)}</td><td>${e(h.status === "Ready" ? __("Ready, kept until {0}", [h.ready_until]) : __("Waiting"))}</td><td class="text-right"><button class="btn btn-xs btn-default" data-cancel-hold="${e(h.name)}">${__("Cancel")}</button></td></tr>`).join("");
		const fines = s.fines.map((f) => `<tr><td>${e(f.reason)} ${e(f.note || "")}</td><td>${e(cur)}${e(f.amount)}</td><td class="text-right"><button class="btn btn-xs btn-default" data-pay="${e(f.name)}">${__("Paid")}</button> <button class="btn btn-xs btn-default" data-waive="${e(f.name)}">${__("Waive")}</button></td></tr>`).join("");
		this.$.find("#rdc-patron").html(`<div class="rdc-card">
			<h4>${e(p.full_name)} <small class="text-muted">${e(p.name)} · ${e(p.category)} · ${e(p.status)}${p.valid_until ? " · " + __("valid until {0}", [e(p.valid_until)]) : ""}</small></h4>
			${s.standing ? `<p class="text-danger"><b>${e(s.standing)}</b></p>` : ""}
			<p><a href="/app/rd-patron/${encodeURIComponent(p.name)}">${__("Open the member")}</a> · <a href="/library/card?patron=${encodeURIComponent(p.name)}" target="_blank">${__("Print the ID card")}</a></p>
			<label for="rdc-lend"><b>${__("Lend a book")}</b> <span class="text-muted">${__("scan its barcode ({0} of {1} books out)", [s.loans.length, s.limits.loans || "∞"])}</span></label>
			<input id="rdc-lend" class="form-control input-sm" autocomplete="off">
			<h5>${__("On loan")}</h5>${loans ? `<table class="table table-sm"><tbody>${loans}</tbody></table>` : `<p class="text-muted">${__("Nothing on loan.")}</p>`}
			${holds ? `<h5>${__("Holds")}</h5><table class="table table-sm"><tbody>${holds}</tbody></table>` : ""}
			${fines ? `<h5>${__("Fines due: {0}{1}", [e(cur), e(s.fines_total)])}</h5><table class="table table-sm"><tbody>${fines}</tbody></table>` : ""}
		</div>`);
		this.$.find("#rdc-lend").focus();
	}

	act(method, args) {
		this.call(method, args, (m) => { this.say(m.message || __("Done."), true); if (m.snapshot) this.render(m.snapshot); else if (this.patron) this.show(this.patron); this.lists(); });
	}

	checkout($i) {
		const code = $i.val().trim();
		if (!code || !this.patron) return;
		this.call("checkout", { patron: this.patron, barcode: code }, (m) => { this.say(m.message, true); this.render(m.snapshot); this.lists(); });
	}

	checkin($i) {
		const code = $i.val().trim();
		if (!code) return;
		this.call("checkin", { barcode: code }, (m) => {
			this.say(m.message, true);
			$i.val("");
			if (this.patron === m.patron) this.show(this.patron);
			this.lists();
		});
	}

	lists() {
		const e = this.e;
		this.call("overview", {}, (m) => {
			this.$.find("#rdc-overdue").html(`<h5>${__("Overdue ({0})", [m.overdue.length])}</h5>` + (m.overdue.length
				? `<table class="table table-sm"><tbody>${m.overdue.map((o) => `<tr><td>${e(o.title)}</td><td><a href="#" data-member="${e(o.patron)}">${e(o.patron_name)}</a></td><td>${e(o.due_on)}</td></tr>`).join("")}</tbody></table>`
				: `<p class="text-muted">${__("Nothing is overdue.")}</p>`));
			this.$.find("#rdc-shelf").html(`<h5>${__("On the hold shelf ({0})", [m.shelf.length])}</h5>` + (m.shelf.length
				? `<table class="table table-sm"><tbody>${m.shelf.map((o) => `<tr><td>${e(o.title)}</td><td>${e(o.patron_name)}</td><td>${e(o.ready_until)}</td></tr>`).join("")}</tbody></table>`
				: `<p class="text-muted">${__("No book is waiting for a member.")}</p>`));
		});
	}
}
