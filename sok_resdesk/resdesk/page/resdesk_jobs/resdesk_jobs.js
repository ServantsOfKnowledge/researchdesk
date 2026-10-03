// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Background Jobs: everything Research Desk is doing in the background, with controls
// to pause and resume runs, hold or cancel queued jobs, pause schedules, pause everything
// (and carry on later) or stop everything at once.

frappe.pages["resdesk-jobs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Background Jobs"), single_column: true });
	const view = new ResDeskJobs(page);
	wrapper.resdesk_jobs = view;
	view.refresh();
};

frappe.pages["resdesk-jobs"].on_page_show = function (wrapper) {
	if (wrapper.resdesk_jobs) wrapper.resdesk_jobs.start();
};

frappe.pages["resdesk-jobs"].on_page_hide = function (wrapper) {
	if (wrapper.resdesk_jobs) wrapper.resdesk_jobs.stop();
};

class ResDeskJobs {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="rdj"></div>').appendTo(page.main);
		this.data = null;

		page.set_primary_action(__("Stop Everything"), () => this.stop_all(), "stop");
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.pause_all_btn = page.add_inner_button(__("Pause All"), () => this.toggle_pause_all());
		this.pause_btn = page.add_inner_button(__("Pause Schedules"), () => this.toggle_pause());
		page.add_menu_item(__("Rebuild Search Index"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("All Ingest Runs"), () => frappe.set_route("List", "RD Ingest Run"));
		page.add_menu_item(__("All Push Runs"), () => frappe.set_route("List", "RD Push Run"));
		page.add_menu_item(__("Frappe job queue (all apps)"), () => frappe.set_route("List", "RQ Job"));
		page.add_menu_item(__("Help for this screen"), () =>
			window.rd_open_help
				? window.rd_open_help("/app/resdesk-help/operations#background-jobs-see-pause-and-stop-what-is-running")
				: frappe.set_route("resdesk-help", "operations")
		);

		this.$body.on("click", "[data-stop-run]", (e) => this.stop_run($(e.currentTarget).data("stop-run"), 0));
		this.$body.on("click", "[data-kill-run]", (e) => this.stop_run($(e.currentTarget).data("kill-run"), 1));
		this.$body.on("click", "[data-cancel-job]", (e) => this.cancel_job($(e.currentTarget).data("cancel-job")));
		this.$body.on("click", "[data-pause-run]", (e) => this.call("pause_run", { run: $(e.currentTarget).data("pause-run") }));
		this.$body.on("click", "[data-resume-run]", (e) => this.call("resume_run", { run: $(e.currentTarget).data("resume-run") }));
		this.$body.on("click", "[data-stop-push]", (e) => this.stop_push($(e.currentTarget).data("stop-push")));
		this.$body.on("click", "[data-hold-job]", (e) => this.call("hold_job", { job_id: $(e.currentTarget).data("hold-job") }));
		this.$body.on("click", "[data-release]", (e) => this.call("release_held", { keys: JSON.stringify([String($(e.currentTarget).data("release"))]) }));
		this.$body.on("click", "[data-discard]", (e) =>
			this.call("release_held", { keys: JSON.stringify([String($(e.currentTarget).data("discard"))]), discard: 1 }, __("Discard this held job? It won't run."))
		);
		this.$body.on("click", "[data-release-all]", () => this.call("release_held", {}));
		this.$body.on("click", "[data-choose-preset]", () => this.choose_preset());
		this.$body.on("click", "[data-renice]", () => this.renice());
		this.$body.on("click", "[data-restart-search]", () =>
			frappe.confirm(__("Restart the search engine? Searching pauses for a minute; waiting tasks are kept and carry on."), () =>
				frappe
					.call({ method: "sok_resdesk.server.request_task", args: { action: "restart", args: JSON.stringify({ service: "search" }) }, freeze: true })
					.then(() => frappe.show_alert({ message: __("Restart requested: see the Server page"), indicator: "green" }))
			)
		);
		this.$body.on("click", "[data-index-missing]", () =>
			frappe.call({ method: "sok_resdesk.search.enqueue_index_missing", freeze: true }).then((r) => {
				frappe.show_alert({ message: __("{0} books queued for the search engine.", [r.message]), indicator: "green" });
				this.refresh();
			})
		);
		this.$body.on("click", "[data-discard-all]", () => this.call("release_held", { discard: 1 }, __("Discard all held jobs? They won't run.")));
		this.$body.on("click", "[data-cancel-search]", () => this.cancel_search());
		this.$body.on("click", "[data-retry-run]", (e) => this.call("retry_run", { run: $(e.currentTarget).data("retry-run") }));
		this.start();
	}

	start() {
		this.stop();
		this.timer = setInterval(() => !document.hidden && this.refresh(true), 5000);
	}

	stop() {
		clearInterval(this.timer);
	}

	call(method, args, confirm_text, then) {
		const go = () =>
			frappe.call({
				method: `sok_resdesk.jobs.${method}`,
				args: args || {},
				freeze: true,
				callback: (r) => {
					if (r.message && r.message.message) frappe.show_alert({ message: r.message.message, indicator: "green" }, 7);
					if (then) then(r.message);
					this.refresh();
				},
			});
		confirm_text ? frappe.confirm(confirm_text, go) : go();
	}

	refresh(quiet) {
		frappe.call({
			method: "sok_resdesk.jobs.overview",
			callback: (r) => {
				this.data = r.message;
				this.render();
			},
			error: () => !quiet && this.$body.html(`<p class="text-danger">${__("Could not load background jobs.")}</p>`),
		});
	}

	stop_all() {
		const d = new frappe.ui.Dialog({
			title: __("Stop everything Research Desk is doing in the background"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__(
						"Cancels every running ingest, removes all queued ingest, re-index and visibility jobs. Books already ingested stay in the catalogue; running a profile again skips them."
					)}</p>`,
				},
				{ fieldname: "pause", fieldtype: "Check", label: __("Also pause scheduled ingests"), default: 1 },
				{
					fieldname: "force",
					fieldtype: "Check",
					label: __("Stop running jobs immediately (otherwise they finish the book they are on, a few seconds)"),
					default: 0,
				},
				{ fieldname: "search", fieldtype: "Check", label: __("Also cancel pending search-engine indexing"), default: 0 },
			],
			primary_action_label: __("Stop Everything"),
			primary_action: (v) => {
				d.hide();
				this.call("stop_all", { force: v.force ? 1 : 0, pause: v.pause ? 1 : 0, search: v.search ? 1 : 0 });
			},
		});
		d.show();
	}

	toggle_pause_all() {
		if (this.data && this.data.paused_all) {
			this.call("resume_all", {});
		} else {
			this.call(
				"pause_all",
				{},
				__(
					"Pause everything Research Desk is doing in the background? Runs are paused where they are, waiting jobs are held, schedules are paused and new jobs wait. Nothing is lost: Resume All carries on from the same place."
				)
			);
		}
	}

	// what the search engine is working on, and what to do when its queue doesn't move
	engine_html(I) {
		const E = I.engine || {};
		const esc = frappe.utils.escape_html;
		const P = E.processing;
		const when = (t) => (t ? frappe.datetime.comment_when(frappe.datetime.convert_to_system_tz(t.replace("T", " ").replace("Z", "").split(".")[0])) : "");
		let html = `<p class="small text-muted" style="margin:2px 0 0">`;
		html += P
			? __("Working on {0} tasks ({1}) since {2}: {3}% done", [P.tasks, esc((P.types || []).join(", ")), when(P.started), P.percent])
			: E.waiting
			? __("Nothing is being worked on.")
			: __("Nothing waiting.");
		if (E.oldest_waiting) html += ` · ${__("oldest waiting since {0}", [when(E.oldest_waiting)])}`;
		html += `</p>`;
		if (I.stalled || I.long_batch) {
			html += `<p class="small text-danger" style="margin:2px 0 0">${
				I.stalled
					? __("The search engine has tasks waiting but isn't working on any: it is stuck.")
					: __("One batch has been running for hours: the search engine may be running out of memory and starting it again.")
			} <button class="btn btn-xs btn-default" data-restart-search>${__("Restart search engine")}</button>
			<a href="/app/resdesk-help/operations#search-indexing-is-stuck">${__("What to check")}</a></p>`;
		}
		if ((E.failed || []).length) {
			html += `<p class="small text-muted" style="margin:2px 0 0">${__("Last failed task")}: ${esc(E.failed[0].type || "")} · ${esc(E.failed[0].error || "")}</p>`;
		}
		return html;
	}

	renice() {
		const P = (this.data && this.data.machine && this.data.machine.priority) || {};
		const d = new frappe.ui.Dialog({
			title: __("Worker priority"),
			fields: [
				{
					fieldname: "nice",
					fieldtype: "Select",
					label: __("Priority of the background workers"),
					options: (P.levels || []).map((l) => ({ value: String(l.nice), label: `${l.nice}: ${l.label}` })),
					default: String(P.wanted != null ? P.wanted : 10),
				},
				{
					fieldtype: "HTML",
					options: `<p class="text-muted small">${__("The workers run the ingests and re-indexing. A lower number gives them a bigger share of the CPU when the machine is busy; the portal and search slow down a little in return. Each worker takes the change on when it starts its next book, nothing is restarted.")}</p>`,
				},
			],
			primary_action_label: __("Apply"),
			primary_action: (v) => {
				d.hide();
				frappe.call({ method: "sok_resdesk.priority.set_worker_priority", args: { nice: v.nice }, freeze: true }).then((r) => {
					frappe.show_alert({ message: r.message.message, indicator: "green" });
					this.refresh();
				});
			},
		});
		d.show();
	}

	choose_preset() {
		const m = (this.data && this.data.machine) || {};
		const d = new frappe.ui.Dialog({
			title: __("How much of the machine may Research Desk use?"),
			fields: [
				{
					fieldname: "preset",
					fieldtype: "Select",
					label: __("Preset"),
					options: ["light", "standard", "server"],
					default: m.requested_preset || (m.limits && m.limits.preset) || "standard",
				},
				{
					fieldtype: "HTML",
					options: `<table class="table table-sm small"><tbody>
						<tr><th>light</th><td>${__("a laptop or a shared computer: 1 worker, search indexing on 1 thread, at most about 3 GB of memory")}</td></tr>
						<tr><th>standard</th><td>${__("a desktop or small server: 2 workers, 2 indexing threads, at most about 6.5 GB of memory")}</td></tr>
						<tr><th>server</th><td>${__("a machine for Research Desk alone: 4 workers, search engine and database uncapped")}</td></tr>
					</tbody></table>
					<p class="text-muted small">${__("Docker's limits are set outside the app, so the choice takes effect when someone runs this on the server:")}</p>
					<pre class="small">./resdesk.sh resources apply</pre>`,
				},
			],
			primary_action_label: __("Choose"),
			primary_action: (v) => {
				d.hide();
				this.call("choose_preset", { preset: v.preset });
			},
		});
		d.show();
	}

	stop_push(run) {
		frappe.confirm(__("Stop push run {0}? Books already sent stay sent.", [run]), () =>
			frappe.call({ method: "sok_resdesk.outbound.cancel", args: { run_name: run }, freeze: true, callback: () => this.refresh() })
		);
	}

	toggle_pause() {
		const paused = this.data && this.data.paused;
		this.call("set_paused", { paused: paused ? 0 : 1 });
	}

	stop_run(run, force) {
		this.call(
			"stop_run",
			{ run, force },
			force
				? __("Stop run {0} immediately? The book being processed right now is rolled back and picked up next time.", [run])
				: __("Stop run {0}? Running batches finish the book they are on, then stop.", [run])
		);
	}

	cancel_job(job_id) {
		this.call("cancel_job", { job_id, force: 1 }, __("Cancel this job?"));
	}

	cancel_search() {
		this.call(
			"cancel_search_tasks",
			{},
			__("Cancel the search engine's pending indexing? Searches keep working with what is already indexed; use Rebuild Search Index later to complete it.")
		);
	}

	// ---- rendering ------------------------------------------------------------------
	render() {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		this.pause_btn.text(d.paused ? __("Resume Schedules") : __("Pause Schedules"));
		this.pause_all_btn.text(d.paused_all ? __("Resume All") : __("Pause All"));

		const pill = (text, color) => `<span class="indicator-pill ${color}">${esc(text)}</span>`;
		const run_link = (r) => `<a href="/app/rd-ingest-run/${encodeURIComponent(r.name)}">${esc(r.name)}</a>`;
		const pct = (r) => (r.total_found ? Math.min(100, Math.round(((r.processed || 0) / r.total_found) * 100)) : 0);
		const ago = (t) => (t ? frappe.datetime.comment_when(t) : "");

		const summary = `
			<div class="rdj-summary">
				<div><b>${d.active_runs.length}</b><span>${__("ingest runs active")}</span></div>
				<div><b>${d.push_runs.length}</b><span>${__("push runs active")}</span></div>
				<div><b>${d.jobs.filter((j) => j.state === "running").length}</b><span>${__("jobs running")}</span></div>
				<div><b>${d.jobs.filter((j) => j.state === "queued").length}</b><span>${__("jobs waiting")}</span></div>
				<div><b>${d.workers}</b><span>${__("workers")}</span></div>
				<div><b>${d.search.pending || 0}</b><span>${__("search-engine tasks")}</span></div>
				<div><b>${d.held.length}</b><span>${__("jobs held")}</span></div>
				<div>${d.paused ? pill(__("Schedules paused"), "orange") : pill(__("Schedules on"), "green")}</div>
			</div>`;

		const active = d.active_runs.length
			? d.active_runs
					.map(
						(r) => `
				<div class="rdj-run">
					<div class="rdj-run__head">
						${run_link(r)} · <b>${esc(r.profile || "")}</b> ${pill(r.status, { Running: "blue", Paused: "orange" }[r.status] || "gray")}
						<span class="text-muted">${esc(r.triggered_by || "")} · ${__("started")} ${ago(r.started_on || r.creation)}</span>
						<span class="rdj-run__actions">
							${
								r.status === "Paused"
									? d.paused_all
										? ""
										: `<button class="btn btn-xs btn-primary" data-resume-run="${esc(r.name)}">${__("Resume")}</button>`
									: `<button class="btn btn-xs btn-default" data-pause-run="${esc(r.name)}">${__("Pause")}</button>`
							}
							<button class="btn btn-xs btn-default" data-stop-run="${esc(r.name)}">${__("Stop")}</button>
							<button class="btn btn-xs btn-danger" data-kill-run="${esc(r.name)}">${__("Stop now")}</button>
						</span>
					</div>
					<div class="progress" style="height:8px;margin:6px 0"><div class="progress-bar" style="width:${pct(r)}%"></div></div>
					<div class="text-muted small">
						${r.processed || 0} / ${r.total_found || "?"} ${__("books")} · ${r.created_count || 0} ${__("new")},
						${r.updated_count || 0} ${__("updated")}, ${r.skipped_count || 0} ${__("unchanged")}, ${r.failed_count || 0} ${__("failed")}
						${r.chunks_total ? ` · ${__("batches left")}: ${r.pending_chunks}/${r.chunks_total}` : ""}
						· ${__("last progress")} ${ago(r.modified)}
					</div>
				</div>`
					)
					.join("")
			: `<p class="text-muted">${__("No ingest is running or paused.")}</p>`;

		const jobs = d.jobs_error
			? `<p class="text-danger">${esc(d.jobs_error)}</p>`
			: d.jobs.length
			? `<table class="table table-sm rdj-table"><thead><tr>
					<th>${__("Job")}</th><th>${__("State")}</th><th>${__("Run")}</th><th>${__("Books")}</th><th>${__("Since")}</th><th></th>
				</tr></thead><tbody>${d.jobs
					.map(
						(j) => `<tr>
					<td>${esc(j.kind)}<div class="text-muted small">${esc(j.short_id)}</div></td>
					<td>${j.state === "running" ? pill(__("Running"), "blue") : pill(__("Waiting"), "gray")}</td>
					<td>${j.run ? `<a href="/app/${String(j.run).startsWith("PUSH-") ? "rd-push-run" : "rd-ingest-run"}/${encodeURIComponent(j.run)}">${esc(j.run)}</a>` : ""}</td>
					<td>${j.items || ""}</td>
					<td class="text-muted small">${ago(j.started_at || j.enqueued_at)}</td>
					<td class="text-right">${
						j.state === "queued" ? `<button class="btn btn-xs btn-default" data-hold-job="${esc(j.id)}">${__("Hold")}</button> ` : ""
					}<button class="btn btn-xs btn-default" data-cancel-job="${esc(j.id)}">${
						j.state === "running" ? __("Stop") : __("Cancel")
					}</button></td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="text-muted">${__("Nothing queued. The workers are idle.")}</p>`;

		const push_link = (r) => `<a href="/app/rd-push-run/${encodeURIComponent(r.name)}">${esc(r.name)}</a>`;
		const pushes = d.push_runs.length
			? d.push_runs
					.map((r) => {
						const done = (r.sent || 0) + (r.unchanged || 0) + (r.skipped || 0) + (r.failed || 0);
						const p = r.total ? Math.min(100, Math.round((done / r.total) * 100)) : 0;
						return `<div class="rdj-run">
					<div class="rdj-run__head">
						${push_link(r)} · <b>${esc(r.target)}</b> ${pill(r.status, { Running: "blue", Paused: "orange" }[r.status] || "gray")}
						${r.dry_run ? pill(__("Dry run"), "gray") : ""}
						<span class="text-muted">${esc(r.triggered_by || "")} · ${ago(r.creation)}</span>
						<span class="rdj-run__actions">
							${
								r.status === "Paused"
									? d.paused_all
										? ""
										: `<button class="btn btn-xs btn-primary" data-resume-run="${esc(r.name)}">${__("Resume")}</button>`
									: `<button class="btn btn-xs btn-default" data-pause-run="${esc(r.name)}">${__("Pause")}</button>`
							}
							<button class="btn btn-xs btn-default" data-stop-push="${esc(r.name)}">${__("Stop")}</button>
						</span>
					</div>
					<div class="progress" style="height:8px;margin:6px 0"><div class="progress-bar" style="width:${p}%"></div></div>
					<div class="text-muted small">${done} / ${r.total || "?"} ${__("books")} · ${r.sent || 0} ${r.dry_run ? __("would be sent") : __("sent")},
						${r.unchanged || 0} ${__("unchanged")}, ${r.skipped || 0} ${__("skipped")}, ${r.failed || 0} ${__("failed")}</div>
				</div>`;
					})
					.join("")
			: `<p class="text-muted">${__("No metadata push is running or paused.")}</p>`;

		const held = d.held.length
			? `<table class="table table-sm rdj-table"><tbody>${d.held
					.map(
						(h) => `<tr><td>${esc(h.kind)}<div class="text-muted small">${esc(h.job_id || "")}</div></td>
					<td>${h.run ? esc(h.run) : ""}</td><td class="text-muted small">${__("held")} ${ago(h.held_on)}</td>
					<td class="text-right">${
						d.paused_all ? "" : `<button class="btn btn-xs btn-default" data-release="${esc(h.key)}">${__("Release")}</button> `
					}<button class="btn btn-xs btn-default" data-discard="${esc(h.key)}">${__("Discard")}</button></td></tr>`
					)
					.join("")}</tbody></table>
				${
					d.paused_all
						? `<p class="text-muted small">${__("These run again when you press Resume All.")}</p>`
						: `<button class="btn btn-xs btn-default" data-release-all>${__("Release all")}</button>`
				}
				<button class="btn btn-xs btn-default" data-discard-all>${__("Discard all")}</button>`
			: `<p class="text-muted">${__("No jobs on hold. Use Hold on a waiting job, or Pause All, to keep jobs for later.")}</p>`;

		const q = d.quiet || {};
		const banner = d.paused_all
			? `<div class="alert alert-warning">${
					q.inside
						? __("Quiet hours ({0} to {1}): everything is paused and carries on by itself at {1}. <b>Resume All</b> carries on now.", [q.from, q.to])
						: __("Everything is paused: runs keep their place, waiting jobs are held, and new jobs wait. Press <b>Resume All</b> to carry on.")
			  }</div>`
			: "";

		const m = d.machine || { host: {}, limits: {} };
		const h = m.host || {};
		const gb = (b) => (b ? (b / 1024 ** 3).toFixed(b >= 10 * 1024 ** 3 ? 0 : 1) + " GB" : "–");
		const bar = (pct, label) => {
			const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
			const color = p > 85 ? "var(--red-500)" : p > 65 ? "var(--orange-500)" : "var(--green-500)";
			return `<div class="rdj-meter"><div class="rdj-meter__label">${label}</div>
				<div class="rdj-meter__bar"><div style="width:${p}%;background:${color}"></div></div></div>`;
		};
		const load = (h.load || [])[0];
		const cpu_pct = h.cpus && load != null ? (load / h.cpus) * 100 : null;
		const mem_used = h.mem_total && h.mem_available != null ? h.mem_total - h.mem_available : null;
		const L = m.limits || {};
		const cap = (v, unit) => (!v || v === "0" ? __("no limit") : `${v}${unit || ""}`);
		const limits = m.native
			? `<p class="text-muted small">${__("Native install: workers {0}; CPU and memory caps are a Docker feature.", [L.workers || "?"])}</p>`
			: `<table class="table table-sm rdj-table small"><tbody>
				<tr><td>${__("Background workers")}</td><td>${
					+L.per_container > 1
						? __("{0} × {1} workers, each container", [esc(L.workers || "1"), esc(L.per_container)])
						: esc(L.workers || "2") + " ×"
				} (${cap(L.worker_cpus, " CPU")}, ${cap(L.worker_memory)}) · ${__("low priority")} (nice ${esc(L.worker_nice || "19")})</td></tr>
				<tr><td>${__("Search engine")}</td><td>${cap(L.search_cpus, " CPU")}, ${cap(L.search_memory)} · ${__("indexing threads")}: ${esc(L.search_threads || __("automatic"))}</td></tr>
				<tr><td>${__("Database")}</td><td>${cap(L.db_cpus, " CPU")}, ${cap(L.db_memory)} · ${__("buffer pool")} ${esc(L.db_buffer_pool || "")}</td></tr>
				<tr><td>${__("Web server")}</td><td>${esc(L.web_workers || "2")} ${__("workers")}</td></tr>
			</tbody></table>`;
		const rows = m.containers
			? `<table class="table table-sm rdj-table small"><thead><tr><th>${__("Part")}</th><th>CPU</th><th>${__("Memory")}</th></tr></thead><tbody>${m.containers
					.map(
						(c) => `<tr><td>${esc(c.name)}${c.number !== "1" ? " " + esc(c.number) : ""}</td><td>${c.cpu}%</td>
						<td>${gb(c.mem)}${c.mem_limit && c.mem_limit < (h.mem_total || Infinity) ? " / " + gb(c.mem_limit) : ""}</td></tr>`
					)
					.join("")}</tbody></table>`
			: m.native
			? ""
			: `<p class="text-muted small">${__("For CPU and memory per part, run on the server:")} <code>./resdesk.sh resources monitor on</code></p>`;
		const preset = L.preset || (m.native ? "" : "standard");
		const P = m.priority || {};
		const started = L.worker_nice != null && L.worker_nice !== "" ? L.worker_nice : null;
		const prio = `<p class="small" style="margin-top:6px">${__("Worker priority")} (nice): <b>${P.wanted != null ? P.wanted : started != null ? started : "–"}</b>
			${P.wanted != null && P.workers ? ` · ${__("{0} of {1} workers on it", [P.applied, P.workers])}` : ""}
			<button class="btn btn-xs btn-default" data-renice style="margin-left:6px">${__("Change")}</button>
			${(P.refused || []).length ? `<br><span class="text-danger">${__("A worker may not lower its niceness here ({0}). To give workers more, run on the server:", [esc(P.refused[0])])} <code>./resdesk.sh resources set WORKER_NICE=${esc(P.wanted)}</code></span>` : ""}</p>`;
		const I = m.indexing;
		const idx = I
			? `<p class="small" style="margin-top:6px">${__("Search index")}: <b>${I.listed.toLocaleString()}</b> ${__("of")} <b>${I.catalogue.toLocaleString()}</b> ${__("books listed to readers")}
				${I.waiting ? ` · ${__("{0} jobs waiting in the search engine", [I.waiting])}` : ""}
				${I.unsent ? `<br><span class="text-warning">${__("{0} books never reached the search engine.", [I.unsent])}</span> <button class="btn btn-xs btn-default" data-index-missing>${__("Send them")}</button>` : ""}</p>
				${this.engine_html(I)}`
			: "";
		const machine = `
			<div class="rdj-machine">
				<div>
					${bar(cpu_pct, `${__("CPU load")}: ${load != null ? load : "–"} ${__("on {0} CPUs", [h.cpus || "?"])}`)}
					${bar(mem_used && h.mem_total ? (mem_used / h.mem_total) * 100 : 0, `${__("Memory")}: ${gb(mem_used)} ${__("of")} ${gb(h.mem_total)}`)}
					${bar(h.disk_total ? ((h.disk_total - h.disk_free) / h.disk_total) * 100 : 0, `${__("Disk")}: ${gb(h.disk_free)} ${__("free")}${m.search_size ? " · " + __("search index") + " " + gb(m.search_size) : ""}`)}
					<p class="small" style="margin-top:10px">${__("Preset in use")}: <b>${esc(preset || "–")}</b>
						${m.requested_preset && m.requested_preset !== preset ? ` · ${__("chosen")}: <b>${esc(m.requested_preset)}</b> (${__("run")} <code>./resdesk.sh resources apply</code>)` : ""}
						${m.native ? "" : `<button class="btn btn-xs btn-default" data-choose-preset style="margin-left:6px">${__("Change")}</button>`}</p>
					${prio}${idx}
					<p class="small text-muted">${
						q.enabled
							? __("Quiet hours: {0} to {1}{2}.", [q.from, q.to, q.weekdays_only ? " " + __("on weekdays") : ""])
							: __("Quiet hours are off.")
					} <a href="/app/rd-settings">${__("Settings → Machine Resources")}</a></p>
				</div>
				<div>${limits}${rows}</div>
			</div>`;

		const schedules = d.schedules.length
			? `<table class="table table-sm rdj-table"><tbody>${d.schedules
					.map(
						(s) => `<tr><td><a href="/app/rd-ingest-profile/${encodeURIComponent(s.name)}">${esc(s.name)}</a></td>
					<td>${esc(s.schedule)}</td><td class="text-muted small">${__("last run")} ${ago(s.last_run_on) || __("never")}</td>
					<td>${esc(s.last_status || "")}</td></tr>`
					)
					.join("")}</tbody></table>
				<p class="text-muted small">${
					d.paused
						? __("Paused: none of these start on their own until you resume schedules.")
						: __("These start on their own. Set a profile's Schedule to Manual to stop it permanently, or pause them all above.")
				}</p>`
			: `<p class="text-muted">${__("No ingest profile runs on a schedule.")}</p>`;

		const search = !d.search.ok
			? `<p class="text-danger">${__("Search engine not reachable")}: ${esc(d.search.error || "")}</p>`
			: d.search.pending
			? `<p>${__("{0} indexing tasks pending ({1} in progress). The search engine is busy updating its index; this uses CPU until it finishes.", [
					d.search.pending,
					d.search.processing,
			  ])}</p>
				<table class="table table-sm rdj-table"><tbody>${d.search.tasks
					.map((t) => `<tr><td>${esc(t.type)}</td><td>${esc(t.index)}</td><td>${esc(t.status)}</td><td class="text-muted small">${esc(t.enqueued_at)}</td></tr>`)
					.join("")}</tbody></table>
				<button class="btn btn-xs btn-default" data-cancel-search>${__("Cancel pending indexing")}</button>`
			: `<p class="text-muted">${__("Idle.")}</p>`;

		const recent = d.recent_runs.length
			? `<table class="table table-sm rdj-table"><tbody>${d.recent_runs
					.map(
						(r) => `<tr><td>${run_link(r)}</td><td>${esc(r.profile || "")}</td>
					<td>${pill(r.status, { Completed: "green", Cancelled: "gray", Interrupted: "orange" }[r.status] || "red")}</td>
					<td class="small">${r.processed || 0} ${__("books")}, ${r.failed_count || 0} ${__("failed")}</td>
					<td class="text-muted small">${ago(r.finished_on || r.modified)}</td>
					<td>${["Completed with Errors", "Interrupted", "Failed", "Cancelled"].includes(r.status)
						? `<button class="btn btn-xs btn-default" data-retry-run="${esc(r.name)}">${r.status === "Completed with Errors" ? __("Retry failed") : __("Carry on")}</button>`
						: ""}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="text-muted">${__("No runs yet.")}</p>`;

		this.$body.html(`
			<style>
				.rdj { padding: 8px 0 40px; }
				.rdj-summary { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
				.rdj-summary > div { border:1px solid var(--border-color); border-radius:8px; padding:10px 14px; min-width:120px;
					display:flex; flex-direction:column; justify-content:center; background:var(--card-bg); }
				.rdj-summary b { font-size:20px; }
				.rdj-summary span { color: var(--text-muted); font-size: 12px; }
				.rdj-card { border:1px solid var(--border-color); border-radius:8px; padding:14px 16px; margin-bottom:16px; background:var(--card-bg); }
				.rdj-card h4 { margin:0 0 10px; font-size:14px; font-weight:600; }
				.rdj-run { padding:8px 0; border-bottom:1px solid var(--border-color); }
				.rdj-run:last-child { border-bottom:0; }
				.rdj-run__head { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
				.rdj-run__actions { margin-left:auto; display:flex; gap:6px; }
				.rdj-table td, .rdj-table th { vertical-align: middle; }
				.rdj-machine { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1.2fr); gap: 24px; }
				@media (max-width: 900px) { .rdj-machine { grid-template-columns: 1fr; } }
				.rdj-meter { margin-bottom: 10px; }
				.rdj-meter__label { font-size: 12px; color: var(--text-muted); margin-bottom: 3px; }
				.rdj-meter__bar { height: 8px; background: var(--gray-200, #eee); border-radius: 4px; overflow: hidden; }
				.rdj-meter__bar div { height: 100%; }
			</style>
			${banner}
			${summary}
			<div class="rdj-card"><h4>${__("Ingest runs in progress")}</h4>${active}</div>
			<div class="rdj-card"><h4>${__("Metadata pushes in progress")}</h4>${pushes}</div>
			<div class="rdj-card"><h4>${__("Background jobs (Research Desk)")}</h4>${jobs}</div>
			<div class="rdj-card"><h4>${__("Held jobs")}</h4>${held}</div>
			<div class="rdj-card"><h4>${__("Machine")}</h4>${machine}</div>
			<div class="rdj-card"><h4>${__("Scheduled ingests")}</h4>${schedules}</div>
			<div class="rdj-card"><h4>${__("Search engine")}</h4>${search}</div>
			<div class="rdj-card"><h4>${__("Recent runs")}</h4>${recent}</div>
			<p class="text-muted small">${__("Updated")} ${esc(d.now)} · ${__("refreshes every 5 seconds")}</p>
		`);
	}
}
