// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Server: versions and updates, the health of every part, backups, logs, alerts and
// resources in one place. With the updater helper on (./resdesk.sh updater on), System
// Managers can also upgrade, restart and apply resource presets from here (docs/server.md).

frappe.pages["resdesk-server"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Server"), single_column: true });
	wrapper.resdesk_server = new ResDeskServer(page);
};
frappe.pages["resdesk-server"].on_page_show = (wrapper) => wrapper.resdesk_server && wrapper.resdesk_server.start();
frappe.pages["resdesk-server"].on_page_hide = (wrapper) => wrapper.resdesk_server && wrapper.resdesk_server.stop();

class ResDeskServer {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="rds"></div>').appendTo(page.main);
		this.data = null;
		this.watching = null; // the task whose log is shown live
		this.log_view = { source: "errors" };

		page.set_primary_action(__("Check for Updates"), () => this.check_updates(), "refresh");
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		page.add_menu_item(__("Settings: Server & Updates"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("All server tasks"), () => frappe.set_route("List", "RD Server Task"));
		page.add_menu_item(__("Error Log"), () => frappe.set_route("List", "Error Log"));
		page.add_menu_item(__("Background Jobs"), () => frappe.set_route("resdesk-jobs"));
		page.add_menu_item(__("Send a test alert"), () => this.call("test_alert"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help ? window.rd_open_help("/app/resdesk-help/server") : frappe.set_route("resdesk-help", "server")
		);

		const on = (sel, fn) => this.$body.on("click", sel, (e) => fn($(e.currentTarget), e));
		on("[data-upgrade]", () => this.upgrade_dialog());
		on("[data-restart]", ($b) => this.restart($b.data("restart")));
		on("[data-server-logs]", ($b) => this.server_logs($b.data("server-logs")));
		on("[data-backup]", ($b) => this.call("take_backup", { with_files: $b.data("backup") === "files" ? 1 : 0 }));
		on("[data-server-backup]", () => this.task("server_backup", {}, __("Back up on the server into site-backups/ (database and files), the same as ./resdesk.sh backup?")));
		on("[data-delete-backup]", ($b) =>
			this.call("delete_backup", { name: $b.data("delete-backup") }, __("Delete this backup? This can't be undone."))
		);
		on("[data-apply-preset]", () => this.apply_preset());
		on("[data-watch]", ($b) => this.watch($b.data("watch")));
		on("[data-cancel-task]", ($b) => this.call("cancel_task", { name: $b.data("cancel-task") }));
		on("[data-log-source]", ($b) => this.load_logs($b.data("log-source")));
		on("[data-retry-job]", ($b) =>
			frappe.call({
				method: "sok_resdesk.jobs.retry_failed_jobs",
				args: { job_id: $b.attr("data-retry-job") || null },
				freeze: true,
				callback: (r) => {
					frappe.show_alert({ message: r.message.message, indicator: "green" }, 8);
					this.load_logs("failed_jobs");
				},
			})
		);
		on("[data-clear-failed]", () =>
			frappe.confirm(__("Clear the list of failed jobs? They won't be tried again."), () =>
				frappe.call({ method: "sok_resdesk.jobs.clear_failed_jobs", freeze: true, callback: (r) => {
					frappe.show_alert({ message: r.message.message, indicator: "green" });
					this.load_logs("failed_jobs");
				} })
			)
		);
		on("[data-copy]", ($b) => frappe.utils.copy_to_clipboard($b.data("copy")));
		on("[data-req-refresh]", () => this.load_requirements(1));
		on("[data-req-install]", ($b) => {
			const part = $b.data("req-install");
			const what = part === "ocr" ? __("Tesseract and its language models") : __("Research Desk's Python packages");
			frappe.confirm(__("Install {0} on this server, through the updater helper?", [what]), () =>
				frappe.call({
					method: "sok_resdesk.requirements.install",
					args: { part },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({ message: __("Started {0}. Its progress shows below.", [r.message]), indicator: "blue" }, 6);
						this.watch(r.message);
						this.req = null;
					},
				})
			);
		});
		this.$body.on("change", "[data-log-file]", (e) => this.load_logs("files", $(e.currentTarget).val()));
		this.refresh();
		this.start();
	}

	start() {
		this.stop();
		this.timer = setInterval(() => !document.hidden && this.refresh(true), 15000);
		if (this.watching) this.poll_task();
	}

	stop() {
		clearInterval(this.timer);
		clearTimeout(this.task_timer);
	}

	call(method, args, confirm_text, then) {
		const go = () =>
			frappe.call({
				method: `sok_resdesk.server.${method}`,
				args: args || {},
				freeze: true,
				callback: (r) => {
					if (r.message && r.message.message) frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
					if (then) then(r.message);
					this.refresh(true);
				},
			});
		confirm_text ? frappe.confirm(confirm_text, go) : go();
	}

	task(action, args, confirm_text) {
		this.call("request_task", { action, args: JSON.stringify(args || {}) }, confirm_text, (name) => {
			frappe.show_alert({ message: __("Started {0}. Its progress shows below.", [name]), indicator: "blue" }, 6);
			this.watch(name);
		});
	}

	refresh(quiet) {
		frappe.call({
			method: "sok_resdesk.server.status",
			callback: (r) => {
				this.offline = false;
				this.data = r.message;
				const active = (this.data.tasks || []).find((t) => ["Queued", "Running"].includes(t.status));
				if (active && !this.watching) this.watch(active.name);
				this.render();
			},
			error: () => {
				if (!quiet) this.$body.html(`<p class="text-danger">${__("Could not load the server status.")}</p>`);
			},
		});
	}

	check_updates() {
		this.call("check_updates", {}, null, () =>
			frappe.show_alert({ message: __("Checked for updates."), indicator: "green" }, 5)
		);
	}

	// ---- tasks -----------------------------------------------------------------------
	watch(name) {
		this.watching = name;
		this.poll_task();
	}

	poll_task() {
		clearTimeout(this.task_timer);
		if (!this.watching) return;
		$.ajax({
			url: "/api/method/sok_resdesk.server.get_task",
			data: { name: this.watching },
			headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
			success: (r) => {
				this.offline = false;
				this.task_doc = r.message;
				this.render_task();
				if (["Queued", "Running"].includes(this.task_doc.status)) {
					this.task_timer = setTimeout(() => this.poll_task(), 3000);
				} else {
					this.refresh(true);
				}
			},
			error: () => {
				// the site restarts during an upgrade or restart: keep trying
				this.offline = true;
				this.render_task();
				this.task_timer = setTimeout(() => this.poll_task(), 5000);
			},
		});
	}

	render_task() {
		const $box = this.$body.find(".rds-task");
		if (!$box.length) return;
		const t = this.task_doc;
		const esc = frappe.utils.escape_html;
		if (!t) return $box.html("");
		const color = { Queued: "gray", Running: "blue", Succeeded: "green", Failed: "red", Cancelled: "gray" }[t.status];
		const running = ["Queued", "Running"].includes(t.status);
		$box.html(`
			<div class="rds-card">
				<h4>${esc(t.title || t.name)} <span class="indicator-pill ${color}">${__(t.status)}</span>
					<a class="small" href="/app/rd-server-task/${encodeURIComponent(t.name)}" style="margin-left:6px">${esc(t.name)}</a>
					${t.status === "Queued" ? `<button class="btn btn-xs btn-default" data-cancel-task="${esc(t.name)}" style="margin-left:6px">${__("Cancel")}</button>` : ""}
				</h4>
				${
					this.offline
						? `<div class="alert alert-info">${__("The server is restarting. This page reconnects by itself; the upgrade carries on meanwhile.")}</div>`
						: t.status === "Queued"
						? `<p class="text-muted small">${__("Waiting for the updater helper to pick it up (a few seconds).")}</p>`
						: ""
				}
				${t.summary && !running ? `<p class="${t.status === "Failed" ? "text-danger" : ""}">${esc(t.summary)}</p>` : ""}
				<pre class="rds-log">${esc(t.log || (running ? __("Starting…") : ""))}</pre>
			</div>`);
		const pre = $box.find(".rds-log")[0];
		if (pre) pre.scrollTop = pre.scrollHeight;
	}

	// ---- actions ---------------------------------------------------------------------
	upgrade_dialog() {
		const u = this.data.updates;
		const releases = (u.releases || []).filter((r) => r !== "v" + u.current);
		const d = new frappe.ui.Dialog({
			title: __("Upgrade Research Desk"),
			fields: [
				{
					fieldname: "target",
					fieldtype: "Select",
					label: __("Release"),
					options: [{ value: "latest", label: __("Latest release ({0})", [u.latest || "?"]) }].concat(
						releases.map((r) => ({ value: r, label: r }))
					),
					default: "latest",
					description: __("Choosing an older release goes back to it (only the code: restore a backup if its database changes are needed)."),
				},
				{ fieldname: "backup", fieldtype: "Check", label: __("Back up first (recommended)"), default: 1 },
				{ fieldname: "frappe", fieldtype: "Check", label: __("Also update Frappe to its newest patch release"), default: 1 },
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__(
						"The portal and the Desk are offline for a few minutes (longer when Frappe is rebuilt). Running ingests and pushes are interrupted and can be resumed afterwards. This page shows the progress and reconnects by itself."
					)}</p>`,
				},
			],
			primary_action_label: __("Upgrade"),
			primary_action: (v) => {
				d.hide();
				this.task("upgrade", { target: v.target, backup: v.backup ? 1 : 0, frappe: v.frappe ? 1 : 0 });
			},
		});
		d.show();
	}

	restart(part) {
		const names = { web: __("the portal and Desk"), workers: __("the background workers"), scheduler: __("the scheduler"), search: __("the search engine"), all: __("everything") };
		this.task("restart", { service: part }, __("Restart {0}? Anything it is doing stops and starts again.", [names[part] || part]));
	}

	server_logs(part) {
		this.task("logs", { service: part, lines: 300 });
	}

	apply_preset() {
		const d = new frappe.ui.Dialog({
			title: __("Apply a resource preset"),
			fields: [
				{ fieldname: "preset", fieldtype: "Select", label: __("Preset"), options: ["light", "standard", "server"], default: this.data.resource_preset || "standard" },
				{ fieldtype: "HTML", options: `<p class="text-muted small">${__("Background workers, search engine and database restart with the new limits (about a minute). See Background Jobs → Machine for what each preset means.")}</p>` },
			],
			primary_action_label: __("Apply"),
			primary_action: (v) => {
				d.hide();
				this.task("apply_resources", { preset: v.preset });
			},
		});
		d.show();
	}

	load_logs(source, name) {
		this.log_view = { source, name: name || "" };
		frappe.call({
			method: "sok_resdesk.server.logs",
			args: { source, name: name || "", lines: 300 },
			callback: (r) => {
				this.log_data = r.message;
				this.render_logs();
			},
		});
	}

	render_logs() {
		const $box = this.$body.find(".rds-logs");
		const esc = frappe.utils.escape_html;
		const v = this.log_view;
		const r = this.log_data || {};
		const tab = (key, label) => `<button class="btn btn-xs ${v.source === key ? "btn-primary" : "btn-default"}" data-log-source="${key}">${label}</button>`;
		let body = "";
		if (!this.log_data) body = `<p class="text-muted small">${__("Loading…")}</p>`;
		else if (v.source === "errors")
			body = r.rows.length
				? `<table class="table table-sm small"><tbody>${r.rows
						.map((e) => `<tr><td class="text-muted" style="white-space:nowrap">${esc(String(e.creation).slice(0, 16))}</td><td><a href="/app/error-log/${e.name}">${esc(e.method || e.name)}</a><div class="text-muted">${esc(e.error)}</div></td></tr>`)
						.join("")}</tbody></table>`
				: `<p class="text-muted">${__("No errors logged.")}</p>`;
		else if (v.source === "failed_jobs")
			body = r.rows.length
				? `<table class="table table-sm small"><tbody>${r.rows
						.map((j) => `<tr><td class="text-muted" style="white-space:nowrap">${esc(j.ended_at)}</td><td>${esc(j.method)}<div class="text-muted">${esc(j.error)}</div></td><td>${esc(j.queue)}</td>
							<td><button class="btn btn-xs btn-default" data-retry-job="${esc(j.id)}">${__("Retry")}</button></td></tr>`)
						.join("")}</tbody></table>
					<div style="display:flex;gap:6px"><button class="btn btn-xs btn-primary" data-retry-job="">${__("Retry all")}</button>
					${this.data && this.data.is_admin ? `<button class="btn btn-xs btn-default" data-clear-failed>${__("Clear the list")}</button>` : ""}</div>
					<p class="text-muted small" style="margin-top:6px">${__("Ingest batches that failed go back into their run, which carries on; other jobs simply run again.")}</p>`
				: `<p class="text-muted">${__("No failed jobs.")}</p>`;
		else if (v.source === "files")
			body = `<select class="form-control input-sm" data-log-file style="max-width:320px;margin-bottom:8px">
					<option value="">${__("Choose a log file")}</option>
					${(r.files || []).map((f) => `<option value="${esc(f.name)}" ${f.name === v.name ? "selected" : ""}>${esc(f.name)} (${Math.ceil(f.size / 1024)} KB, ${esc(f.modified)})</option>`).join("")}
				</select>${r.text ? `<pre class="rds-log">${esc(r.text)}</pre>` : ""}`;
		$box.html(`<div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap">
			${tab("errors", __("Errors"))}${tab("failed_jobs", __("Failed jobs"))}${tab("files", __("Log files"))}
		</div>${body}`);
		const pre = $box.find(".rds-log")[0];
		if (pre) pre.scrollTop = pre.scrollHeight;
	}

	// ---- rendering -------------------------------------------------------------------
	render() {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		const u = d.updates;
		const h = d.helper;
		const can_act = h.configured && h.connected && d.is_admin && h.allowed;
		const pill = (text, color) => `<span class="indicator-pill ${color}">${esc(text)}</span>`;
		const state_pill = { ok: pill(__("OK"), "green"), warn: pill(__("Check"), "orange"), bad: pill(__("Problem"), "red"), off: pill(__("Off"), "gray"), info: pill(__("New"), "blue") };
		const gb = (b) => (b ? (b / 1024 ** 3).toFixed(1) + " GB" : "–");
		const mb = (b) => (b >= 1024 ** 3 ? gb(b) : Math.max(1, Math.round(b / 1024 ** 2)) + " MB");
		const cmd = (text) => `<div class="rds-cmd"><code>${esc(text)}</code><button class="btn btn-xs btn-default" data-copy="${esc(text)}">${__("Copy")}</button></div>`;

		const cap = d.capacity || {};
		const bad = d.health.filter((c) => c.state === "bad").length;
		const m = cap.machine || {};
		const res = m.books || {};
		const res_row = (key, label, have) =>
			res[key] != null
				? `<tr><td>${label}</td><td class="text-muted">${have}</td><td>${__("about {0} books", [res[key].toLocaleString()])}</td>
					<td>${m.by === key ? pill(__("the limit"), "blue") : ""}</td></tr>`
				: "";
		const capacity = `
			<p>${
				cap.mode === "none"
					? __("No book limit is set.")
					: cap.limit_books
					? __("{0} books ({1} pages of text) of a limit of about <b>{2}</b>: room for about {3} more.", [
							(cap.books || 0).toLocaleString(),
							(cap.pages || 0).toLocaleString(),
							cap.limit_books.toLocaleString(),
							(cap.remaining_books || 0).toLocaleString(),
					  ])
					: __("The limit couldn't be worked out on this machine.")
			} ${cap.mode === "custom" ? __("(a number chosen in Settings)") : cap.mode === "auto" ? __("(what this machine can hold)") : ""}</p>
			${
				cap.limit_units
					? `<div class="rdj-meter__bar" style="height:8px;background:var(--gray-200,#eee);border-radius:4px;overflow:hidden;margin-bottom:10px"><div style="height:100%;width:${Math.min(
							100,
							cap.percent || 0
					  )}%;background:${cap.percent >= 100 ? "var(--red-500)" : cap.percent >= 90 ? "var(--orange-500)" : "var(--green-500)"}"></div></div>`
					: ""
			}
			${cap.full ? `<div class="alert alert-danger small">${__("The limit is reached: ingests keep updating the books already here but add no new ones.")}</div>` : ""}
			${
				m.known
					? `<table class="table table-sm rds-table small"><thead><tr><th>${__("This machine")}</th><th></th><th>${__("can hold")}</th><th></th></tr></thead><tbody>
					${res_row("cpu", __("CPUs"), cap.host.cpus || "?")}
					${res_row("memory", __("Memory"), gb(cap.host.mem_total))}
					${res_row("disk", __("Disk"), `${gb(cap.host.disk_free)} ${__("free")}`)}
				</tbody></table>
				<p class="text-muted small">${__("Estimated at this library's average of {0} pages per book, from sizes measured on real books. Books with more pages use more of the limit.", [
					cap.pages_per_book,
				])}</p>`
					: ""
			}
			<a class="small" href="/app/rd-settings">${__("Settings → Machine Resources → Book Limit")}</a>`;
		const summary = `
			<div class="rds-summary">
				<div><span>${__("Research Desk")}</span><b>v${esc(d.version)}</b>${u.newer ? pill(__("{0} available", [u.latest]), "blue") : ""}</div>
				<div><span>${__("Frappe")}</span><b>${esc(d.frappe)}</b>${u.frappe_newer ? pill(__("{0} available", [u.frappe_latest]), "blue") : ""}</div>
				<div><span>${__("Install")}</span><b>${esc(d.mode === "native" ? __("Native") : "Docker")}</b><small class="text-muted">${esc(d.site)}</small></div>
				<div><span>${__("Health")}</span><b>${bad === 1 ? __("1 problem") : bad ? __("{0} problems", [bad]) : __("All good")}</b></div>
				<div><span>${__("Books")}</span><b>${(cap.books || 0).toLocaleString()}</b><small class="text-muted">${
					cap.limit_books ? __("of about {0} ({1}%)", [cap.limit_books.toLocaleString(), cap.percent]) : __("no limit")
				}</small></div>
				<div><span>${__("Disk")}</span><b>${d.disk.percent}%</b><small class="text-muted">${gb(d.disk.free)} ${__("free")}</small></div>
				<div><span>${__("Updater helper")}</span><b>${h.configured ? (h.connected ? __("Connected") : __("Not reporting")) : __("Off")}</b></div>
			</div>`;

		const health = `<table class="table table-sm rds-table"><tbody>${d.health
			.map(
				(c) => `<tr><td style="width:190px">${esc(c.label)}</td><td style="width:90px">${state_pill[c.state] || ""}</td>
				<td>${esc(c.detail)}${c.link ? ` <a class="small" href="${esc(c.link)}">${__("Open")}</a>` : ""}</td></tr>`
			)
			.join("")}</tbody></table>`;

		const notes = (u.notes || [])
			.map((n) => `<div class="rds-note"><b>${esc(n.version)}</b> <span class="text-muted">${esc(n.date)}</span> ${esc(n.title)}<div class="small">${frappe.markdown(n.notes || "")}</div></div>`)
			.join("");
		const upgrade_cmd = u.latest ? `./upgrade.sh` : "./upgrade.sh";
		const updates = `
			<p>${
				u.newer
					? __("Research Desk <b>{0}</b> is available; this server runs v{1}.", [esc(u.latest), esc(u.current)])
					: u.latest
					? __("Up to date: v{0} is the latest release.", [esc(u.current)])
					: __("Not checked yet. Press Check for Updates.")
			}
			${u.frappe_newer ? " " + __("Frappe {0} is available (this server runs {1}); it is installed with the next upgrade.", [esc(u.frappe_latest), esc(u.frappe)]) : ""}</p>
			${u.error ? `<p class="text-muted small">${esc(u.error)}</p>` : ""}
			${u.needs_reindex ? `<div class="alert alert-warning small">${__("This upgrade changes the search index: rebuild it afterwards (Settings → Rebuild Search Index).")}</div>` : ""}
			${notes ? `<details ${u.newer ? "open" : ""}><summary>${__("What's new")}</summary>${notes}</details>` : ""}
			<div style="margin-top:10px">${
				can_act
					? `<button class="btn btn-sm ${u.newer ? "btn-primary" : "btn-default"}" data-upgrade>${u.newer ? __("Upgrade to {0}", [esc(u.latest)]) : __("Upgrade or reinstall…")}</button>`
					: `<p class="small text-muted">${
							h.configured && !h.allowed
								? __("Upgrades from the Desk are switched off in Settings → Server & Updates. On the server, run:")
								: !d.is_admin
								? __("A System Manager can upgrade from here, or on the server:")
								: __("On the server, in the Research Desk folder, run:")
					  }</p>${cmd(upgrade_cmd)}${
							!h.configured && d.is_admin
								? `<p class="small text-muted">${__("To upgrade from this page instead, turn on the updater helper once on the server:")}</p>${cmd("./resdesk.sh updater on")}`
								: ""
					  }`
			}</div>
			<p class="text-muted small" style="margin-top:8px">${__("Last checked")}: ${u.checked_on ? frappe.datetime.comment_when(u.checked_on) : __("never")}
				${h.git && h.git.local_changes ? ` · <span class="text-danger">${__("The server's Research Desk folder has local code changes; an upgrade will refuse to run until they are committed or stashed.")}</span>` : ""}</p>`;

		const last = d.last_backup || {};
		const backups = `
			<p>${__("Automatic backups")}: <b>${__(d.backup_schedule)}</b>${d.backup_schedule !== "Off" ? ` · ${__("keep {0}", [d.backup_keep])}${d.backup_with_files ? " · " + __("with uploaded files") : ""}` : ""}
				· <a href="/app/rd-settings">${__("Change")}</a>
				${last.when ? ` · ${__("last")}: ${frappe.datetime.comment_when(last.when)} ${last.ok ? pill(__("OK"), "green") : pill(__("Failed"), "red")}` : ""}</p>
			${last.ok === false ? `<p class="text-danger small">${esc(last.error || "")}</p>` : ""}
			<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">
				<button class="btn btn-xs btn-default" data-backup="db">${__("Back up now")}</button>
				<button class="btn btn-xs btn-default" data-backup="files">${__("Back up with files")}</button>
				${can_act ? `<button class="btn btn-xs btn-default" data-server-backup>${__("Back up on the server (site-backups/)")}</button>` : ""}
			</div>
			${
				d.backups.length
					? `<table class="table table-sm rds-table small"><tbody>${d.backups
							.map(
								(b) => `<tr><td style="white-space:nowrap">${esc(b.when)}</td><td>${mb(b.size)}</td>
						<td>${b.files
							.map((f) => (d.is_admin ? `<a href="/backups/${encodeURIComponent(f.name)}">${esc(__(f.kind))}</a>` : esc(__(f.kind))))
							.join(" · ")}</td>
						<td class="text-right">${d.is_admin ? `<button class="btn btn-xs btn-default" data-delete-backup="${esc(b.name)}">${__("Delete")}</button>` : ""}</td></tr>`
							)
							.join("")}</tbody></table>
					<p class="text-muted small">${__("Backups are kept on the server's disk: download them now and then and keep a copy somewhere else. Downloading needs the System Manager role. Restoring is done on the server:")} <code>./resdesk.sh restore FILE</code></p>`
					: `<p class="text-muted">${__("No backups yet.")}</p>`
			}`;

		const parts = [
			["web", __("Portal and Desk")],
			["workers", __("Background workers")],
			["scheduler", __("Scheduler")],
			["search", __("Search engine")],
		];
		const services = h.connected
			? `${
					h.services.length
						? `<table class="table table-sm rds-table small"><thead><tr><th>${__("Part")}</th><th>${__("State")}</th><th>${__("Status")}</th><th></th></tr></thead><tbody>${h.services
								.map(
									(s) => `<tr><td>${esc(s.name || s.service)}</td><td>${pill(s.state || "?", s.state === "running" ? (s.health === "unhealthy" ? "orange" : "green") : "red")}</td>
							<td class="text-muted">${esc(s.status || "")}${s.health ? " · " + esc(s.health) : ""}</td>
							<td class="text-right">${d.mode === "docker" && s.service ? `<button class="btn btn-xs btn-default" data-server-logs="${esc(s.service)}">${__("Logs")}</button>` : ""}</td></tr>`
								)
								.join("")}</tbody></table>`
						: ""
			  }
				${
					can_act
						? `<div style="display:flex;gap:6px;flex-wrap:wrap">${
								d.mode === "docker" ? parts.map(([k, l]) => `<button class="btn btn-xs btn-default" data-restart="${k}">${__("Restart")} ${esc(l)}</button>`).join("") : ""
						  }<button class="btn btn-xs btn-default" data-restart="all">${__("Restart everything")}</button></div>`
						: ""
				}`
			: `<p class="text-muted small">${__("The health list above shows whether each part answers. To see every container or process, restart parts and read their logs from here, turn on the updater helper. On the server:")}</p>${cmd("./resdesk.sh status")}${cmd("./resdesk.sh restart")}`;

		const resources = `
			<p>${__("Preset chosen")}: <b>${esc(d.resource_preset || __("standard (default)"))}</b>.
				<a href="/app/resdesk-jobs">${__("Background Jobs → Machine")}</a> ${__("shows the load and the limits in force.")}</p>
			${
				can_act
					? `<button class="btn btn-xs btn-default" data-apply-preset>${__("Apply a preset now")}</button>`
					: `<p class="small text-muted">${__("Presets are applied on the server:")}</p>${cmd("./resdesk.sh resources apply")}`
			}`;

		const a = d.alerts;
		const alerts = `
			<p class="small">${__("Managers get an alert in the Desk when a part stops working and again when it is fine, when the disk is nearly full, when a backup or upgrade fails, and when a new release is out.")}</p>
			<ul class="small">
				<li>${__("Desk notifications")}: ${pill(__("On"), "green")}</li>
				<li>${__("Email")}: ${a.email ? (a.email_ready ? pill(__("On"), "green") : pill(__("On, but no outgoing email account"), "orange")) : pill(__("Off"), "gray")}</li>
				<li>${__("Webhook")}: ${a.webhook ? pill(__("On"), "green") : pill(__("Not set"), "gray")}</li>
			</ul>
			<a class="small" href="/app/rd-settings">${__("Settings → Server & Updates")}</a> · <a class="small" href="#" onclick="frappe.call({method:'sok_resdesk.server.test_alert',callback:r=>frappe.show_alert({message:r.message.message,indicator:'green'})});return false;">${__("Send a test alert")}</a>
			<p class="small text-muted" style="margin-top:8px">${__("Uptime monitors can check")} <code>${esc(location.origin)}/api/method/sok_resdesk.server.ping</code> ${__("(answers ok, or 503 when something is wrong).")}</p>`;

		const helper = h.configured
			? `<p>${h.connected ? pill(__("Connected"), "green") : pill(__("Not reporting"), "red")}
				${h.seen ? `<span class="text-muted small">${__("last seen")} ${frappe.datetime.comment_when(h.seen)}</span>` : ""}</p>
				${!h.connected ? `<p class="small">${__("Check it on the server:")}</p>${cmd("./resdesk.sh updater status")}` : ""}
				${h.git && h.git.head ? `<p class="small text-muted">${__("Code on the server")}: ${esc(h.git.describe || h.git.head)}${h.git.branch ? " (" + esc(h.git.branch) + ")" : ""}</p>` : ""}
				<p class="small text-muted">${__("It carries out upgrades, restarts and server backups started here by a System Manager, and nothing else. Turn it off on the server with")} <code>./resdesk.sh updater off</code>.</p>`
			: `<p class="small">${__("Off. Upgrades and restarts are done on the server; this page shows the command. Turn the helper on once, on the server, to do them from here:")}</p>${cmd("./resdesk.sh updater on")}
				<p class="small text-muted">${__("It is a small extra container (Docker) or process (native) that can control Docker and this install, so it is off unless you choose it.")}</p>`;

		const tasks = d.tasks.length
			? `<table class="table table-sm rds-table small"><tbody>${d.tasks
					.map(
						(t) => `<tr><td><a href="#" data-watch="${esc(t.name)}">${esc(t.title || t.name)}</a></td>
					<td>${pill(__(t.status), { Queued: "gray", Running: "blue", Succeeded: "green", Failed: "red", Cancelled: "gray" }[t.status])}</td>
					<td class="text-muted">${esc(t.requested_by || "")}</td><td class="text-muted">${frappe.datetime.comment_when(t.creation)}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="text-muted small">${__("Nothing yet.")}</p>`;

		this.$body.html(`
			<style>
				.rds { padding: 8px 0 40px; }
				.rds-summary { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-bottom:16px; }
				.rds-summary > div { border:1px solid var(--border-color); border-radius:8px; padding:10px 14px; background:var(--card-bg); display:flex; flex-direction:column; gap:2px; }
				.rds-summary span { color: var(--text-muted); font-size:12px; }
				.rds-summary b { font-size:18px; }
				.rds-summary .indicator-pill { align-self:flex-start; margin-top:4px; }
				.rds-grid { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap:16px; }
				@media (max-width: 1000px) { .rds-grid { grid-template-columns: 1fr; } }
				.rds-card { border:1px solid var(--border-color); border-radius:8px; padding:14px 16px; margin-bottom:16px; background:var(--card-bg); }
				.rds-card h4 { margin:0 0 10px; font-size:14px; font-weight:600; display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
				.rds-table td, .rds-table th { vertical-align: middle; }
				.rds-log { max-height: 360px; overflow:auto; font-size:12px; background: var(--subtle-fg, #f7f7f7); padding:10px; border-radius:6px; white-space: pre-wrap; }
				.rds-cmd { display:flex; gap:8px; align-items:center; margin:4px 0 8px; }
				.rds-cmd code { padding:4px 8px; }
				.rds-note { border-left:3px solid var(--border-color); padding:4px 10px; margin:8px 0; }
				.rds-note ul { margin-bottom: 0; padding-left: 18px; }
			</style>
			${summary}
			<div class="rds-task"></div>
			<div class="rds-grid">
				<div>
					<div class="rds-card"><h4>${__("Health")}</h4>${health}</div>
					<div class="rds-card" id="requirements"><h4>${__("Requirements")}
						<button class="btn btn-xs btn-default" data-req-refresh style="margin-left:auto">${__("Check again")}</button></h4>
						<div class="rds-req">${this.req ? "" : `<p class="text-muted small">${__("Checking…")}</p>`}</div></div>
					<div class="rds-card"><h4>${__("Book limit")}</h4>${capacity}</div>
					<div class="rds-card"><h4>${__("Updates")}</h4>${updates}</div>
					<div class="rds-card"><h4>${__("Services")}</h4>${services}</div>
					<div class="rds-card"><h4>${__("Recent server tasks")}</h4>${tasks}</div>
				</div>
				<div>
					<div class="rds-card"><h4>${__("Backups")}</h4>${backups}</div>
					<div class="rds-card"><h4>${__("Logs")}</h4><div class="rds-logs"></div></div>
					<div class="rds-card"><h4>${__("Resources")}</h4>${resources}</div>
					<div class="rds-card"><h4>${__("Alerts")}</h4>${alerts}</div>
					<div class="rds-card"><h4>${__("Updater helper")}</h4>${helper}</div>
				</div>
			</div>
			<p class="text-muted small">${__("Updated")} ${esc(d.now)} · ${__("refreshes every 15 seconds")}</p>
		`);
		if (this.task_doc) this.render_task();
		if (this.log_data) this.render_logs();
		else this.load_logs(this.log_view.source, this.log_view.name);
		if (this.req) this.render_requirements();
		else if (!this.req_loading) this.load_requirements(0);
	}

	// ---- requirements: what the server has, and installing what is missing ----------------
	load_requirements(refresh) {
		this.req_loading = true;
		frappe.call({
			method: "sok_resdesk.requirements.report",
			args: { refresh: refresh ? 1 : 0 },
			callback: (r) => {
				this.req = r.message;
				this.req_loading = false;
				this.render_requirements();
			},
			error: () => (this.req_loading = false),
		});
	}

	render_requirements() {
		const esc = frappe.utils.escape_html;
		const d = this.req;
		const pill = { ok: ["green", __("ok")], missing: ["red", __("missing")], old: ["orange", __("too old")], warn: ["orange", __("check")], off: ["gray", __("not needed now")] };
		let group = null;
		const rows = d.items
			.map((i) => {
				const [color, word] = pill[i.state] || ["gray", i.state];
				const head = i.group !== group ? `<tr><th colspan="3" class="text-muted small" style="padding-top:12px">${esc((group = i.group))}</th></tr>` : "";
				const bad = ["missing", "old"].includes(i.state);
				const action = !bad || !i.fix
					? ""
					: i.install && d.can_install
						? `<button class="btn btn-xs btn-primary" data-req-install="${esc(i.install)}">${__("Install")}</button>`
						: `<div class="rds-cmd"><code>${esc(i.fix)}</code>${i.fix.startsWith("./") || i.fix.startsWith("sudo") || i.fix.startsWith("brew") ? `<button class="btn btn-xs btn-default" data-copy="${esc(i.fix)}">${__("Copy")}</button>` : ""}</div>`;
				return `${head}<tr><td><b>${esc(i.label)}</b><div class="text-muted small">${esc(i.purpose)}</div></td>
					<td><span class="indicator-pill ${color}">${word}</span><div class="small">${esc(i.found || "")}${i.need && bad ? ` · ${__("needs")} ${esc(i.need)}` : ""}</div></td>
					<td>${action}</td></tr>`;
			})
			.join("");
		const s = d.summary;
		const intro = `<p class="small">${__("{0} in place · {1} missing or too old · {2} to check", [s.ok, s.missing, s.warn])}
			· ${d.mode === "docker" ? __("Docker install: tools come with the image (upgrade to update them).") : d.can_install ? __("Native install: missing tools can be installed from here.") : __("Native install: turn on the updater helper to install from here, or run the commands shown.")}</p>`;
		this.$body.find(".rds-req").html(`${intro}<table class="table table-sm rds-table"><tbody>${rows}</tbody></table>`);
	}
}
