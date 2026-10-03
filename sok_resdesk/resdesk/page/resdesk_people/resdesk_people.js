// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// People & Roles: each Research Desk role with its people; give or take a role with one click,
// invite people by email, switch accounts off or on, decide sign-ups (sok_resdesk/people.py).

frappe.pages["resdesk-people"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("People & Roles"), single_column: true });
	wrapper.resdesk_people = new ResDeskPeople(page);
};

frappe.pages["resdesk-people"].on_page_show = function (wrapper) {
	wrapper.resdesk_people && wrapper.resdesk_people.refresh();
};

class ResDeskPeople {
	constructor(page) {
		this.page = page;
		this.role = "";
		this.q = "";
		this.show_disabled = 0;
		this.$body = $('<div class="rdp"></div>').appendTo(page.main);
		page.set_primary_action(__("Invite people"), () => this.invite(), "add");
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		page.add_menu_item(__("All accounts (Frappe)"), () => frappe.set_route("List", "User"));
		page.add_menu_item(__("Sign-up requests"), () => frappe.set_route("List", "RD Reader Request"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/staff-guide#people-and-roles") : frappe.set_route("resdesk-help", "staff-guide")
		);
		this.$body.on("click", "[data-role-filter]", (e) => {
			const r = $(e.currentTarget).data("role-filter");
			this.role = this.role === r ? "" : r;
			this.load_users();
			this.paint_roles();
		});
		this.$body.on("change", "[data-toggle-role]", (e) => {
			const $c = $(e.currentTarget);
			this.call("set_role", { user: $c.data("user"), role: $c.data("toggle-role"), on: $c.is(":checked") ? 1 : 0 }, () => $c.prop("checked", !$c.is(":checked")));
		});
		this.$body.on("click", "[data-enable]", (e) => {
			const $b = $(e.currentTarget);
			const on = Number($b.data("enable"));
			const go = () => this.call("set_enabled", { user: $b.data("user"), enabled: on });
			on ? go() : frappe.confirm(__("Switch off {0}? They can't log in until switched on again; their notes and work stay.", [$b.data("user")]), go);
		});
		this.$body.on("click", "[data-decide]", (e) => {
			const $b = $(e.currentTarget);
			frappe.call({ method: "sok_resdesk.people.decide", args: { names: JSON.stringify([$b.data("name")]), status: $b.data("decide") } }).then(() => this.refresh());
		});
		this.$body.on("input", ".rdp-search", frappe.utils.debounce((e) => {
			this.q = e.target.value;
			this.load_users();
		}, 300));
		this.$body.on("change", ".rdp-disabled", (e) => {
			this.show_disabled = e.target.checked ? 1 : 0;
			this.load_users();
		});
	}

	call(method, args, undo) {
		return frappe
			.call({ method: `sok_resdesk.people.${method}`, args })
			.then((r) => {
				frappe.show_alert({ message: __("Saved"), indicator: "green" });
				this.refresh();
				return r;
			})
			.catch(() => undo && undo());
	}

	refresh() {
		frappe.call("sok_resdesk.people.overview").then((r) => {
			this.data = r.message;
			this.render();
			this.load_users();
		});
	}

	render() {
		const esc = frappe.utils.escape_html;
		const reqs = this.data.requests;
		this.$body.html(`
			<style>
				.rdp { padding: 12px 24px 48px; }
				.rdp-roles { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-bottom: 20px; }
				.rdp-role { border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 14px; cursor: pointer; background: var(--card-bg); text-align: left; }
				.rdp-role.active { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
				.rdp-role b { display: block; font-size: 14px; }
				.rdp-role .count { font-size: 22px; font-weight: 600; }
				.rdp-role p { margin: 4px 0 0; color: var(--text-muted); font-size: 12px; }
				.rdp-tools { display: flex; gap: 12px; align-items: center; margin: 8px 0 12px; flex-wrap: wrap; }
				.rdp-search { max-width: 320px; }
				.rdp table { width: 100%; }
				.rdp td, .rdp th { padding: 8px 10px; vertical-align: middle; border-bottom: 1px solid var(--border-color); }
				.rdp th { font-size: 12px; color: var(--text-muted); font-weight: 500; }
				.rdp th.r, .rdp td.r { text-align: center; }
				.rdp .off { opacity: .55; }
				.rdp-req { border: 1px solid var(--yellow-300, #f5d76e); border-radius: 10px; padding: 12px 14px; margin-bottom: 20px; }
				.rdp-req li { margin: 6px 0; }
			</style>
			${reqs.length ? `<div class="rdp-req"><b>${__("Sign-ups waiting for approval")} (${reqs.length})</b><ul class="list-unstyled">${reqs
				.map((r) => `<li>${esc(r.full_name || "")} &lt;${esc(r.email || r.user)}&gt; <span class="text-muted">${esc(r.creation)}</span>
					<button class="btn btn-xs btn-primary" data-decide="Approved" data-name="${esc(r.name)}">${__("Approve")}</button>
					<button class="btn btn-xs btn-default" data-decide="Rejected" data-name="${esc(r.name)}">${__("Reject")}</button></li>`)
				.join("")}</ul></div>` : ""}
			<div class="rdp-roles"></div>
			<div class="rdp-tools">
				<input type="search" class="form-control rdp-search" placeholder="${__("Find by name or email")}" value="${esc(this.q)}">
				<label class="text-muted small"><input type="checkbox" class="rdp-disabled" ${this.show_disabled ? "checked" : ""}> ${__("Show switched-off accounts")}</label>
				<span class="text-muted small rdp-filter"></span>
			</div>
			<div class="rdp-users"></div>`);
		this.paint_roles();
	}

	paint_roles() {
		const esc = frappe.utils.escape_html;
		this.$body.find(".rdp-roles").html(
			this.data.roles
				.map((r) => `<button type="button" class="rdp-role ${this.role === r.role ? "active" : ""}" data-role-filter="${esc(r.role)}">
					<span class="count">${r.count}</span> <b>${esc(r.role.replace("ResDesk ", ""))}</b>
					<p>${esc(r.description)}</p><p>${r.desk ? __("Works in the Desk") : __("Portal only")}</p></button>`)
				.join("")
		);
		this.$body.find(".rdp-filter").text(this.role ? __("Showing: {0} (click the card again for everyone)", [this.role]) : "");
	}

	load_users() {
		frappe.call({ method: "sok_resdesk.people.users", args: { role: this.role, q: this.q, show_disabled: this.show_disabled } }).then((r) => this.paint_users(r.message || []));
	}

	paint_users(rows) {
		const esc = frappe.utils.escape_html;
		const roles = this.data.roles;
		if (!rows.length) return this.$body.find(".rdp-users").html(`<p class="text-muted">${__("Nobody here yet. Invite people with the button above.")}</p>`);
		this.$body.find(".rdp-users").html(`<table>
			<thead><tr><th>${__("Person")}</th>${roles.map((r) => `<th class="r">${esc(r.role.replace("ResDesk ", ""))}</th>`).join("")}<th>${__("Last login")}</th><th></th></tr></thead>
			<tbody>${rows
				.map((u) => `<tr class="${u.enabled ? "" : "off"}">
					<td><a href="/app/user/${encodeURIComponent(u.name)}">${esc(u.full_name || u.name)}</a><br><span class="text-muted small">${esc(u.name)} · ${u.desk ? __("staff") : __("portal")}</span></td>
					${roles
						.map((r) => `<td class="r"><input type="checkbox" data-user="${esc(u.name)}" data-toggle-role="${esc(r.role)}" ${u.roles.includes(r.role) ? "checked" : ""}
							${!r.can_grant || u.name === this.data.me ? "disabled" : ""} aria-label="${esc(r.role)}"></td>`)
						.join("")}
					<td class="small text-muted">${esc(u.last_login || __("never"))}</td>
					<td>${u.name === this.data.me ? "" : u.enabled
						? `<button class="btn btn-xs btn-default" data-enable="0" data-user="${esc(u.name)}">${__("Switch off")}</button>`
						: `<button class="btn btn-xs btn-default" data-enable="1" data-user="${esc(u.name)}">${__("Switch on")}</button>`}</td></tr>`)
				.join("")}</tbody></table>`);
	}

	invite() {
		const d = new frappe.ui.Dialog({
			title: __("Invite people"),
			fields: [
				{ fieldname: "emails", fieldtype: "Small Text", label: __("Email addresses"), reqd: 1, description: __("One per line, or separated by commas.") },
				{ fieldname: "full_name", fieldtype: "Data", label: __("Name (for one person)") },
				{
					fieldname: "roles", fieldtype: "MultiCheck", label: __("Roles"), reqd: 1, columns: 2,
					options: this.data.roles.filter((r) => r.can_grant).map((r) => ({ label: r.role, value: r.role, checked: r.role === "ResDesk Reader" })),
				},
				{ fieldname: "send_welcome", fieldtype: "Check", label: __("Send a welcome email to new accounts"), default: 1 },
			],
			primary_action_label: __("Invite"),
			primary_action: (v) => {
				frappe.call({ method: "sok_resdesk.people.invite", args: { emails: v.emails, roles: JSON.stringify(v.roles || []), full_name: v.full_name || "", send_welcome: v.send_welcome ? 1 : 0 } }).then((r) => {
					d.hide();
					frappe.msgprint(r.message.message);
					this.refresh();
				});
			},
		});
		d.show();
	}
}
