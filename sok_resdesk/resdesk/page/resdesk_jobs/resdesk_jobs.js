// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Background Jobs: everything Research Desk is doing in the background, with controls
// to stop runs, cancel queued jobs, pause schedules or stop everything at once.

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
		this.pause_btn = page.add_inner_button(__("Pause Schedules"), () => this.toggle_pause());
		page.add_menu_item(__("Rebuild Search Index"), () => frappe.set_route("Form", "RD Settings"));
		page.add_menu_item(__("All Ingest Runs"), () => frappe.set_route("List", "RD Ingest Run"));
		page.add_menu_item(__("Frappe job queue (all apps)"), () => frappe.set_route("List", "RQ Job"));

		this.$body.on("click", "[data-stop-run]", (e) => this.stop_run($(e.currentTarget).data("stop-run"), 0));
		this.$body.on("click", "[data-kill-run]", (e) => this.stop_run($(e.currentTarget).data("kill-run"), 1));
		this.$body.on("click", "[data-cancel-job]", (e) => this.cancel_job($(e.currentTarget).data("cancel-job")));
		this.$body.on("click", "[data-cancel-search]", () => this.cancel_search());
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

		const pill = (text, color) => `<span class="indicator-pill ${color}">${esc(text)}</span>`;
		const run_link = (r) => `<a href="/app/rd-ingest-run/${encodeURIComponent(r.name)}">${esc(r.name)}</a>`;
		const pct = (r) => (r.total_found ? Math.min(100, Math.round(((r.processed || 0) / r.total_found) * 100)) : 0);
		const ago = (t) => (t ? frappe.datetime.comment_when(t) : "");

		const summary = `
			<div class="rdj-summary">
				<div><b>${d.active_runs.length}</b><span>${__("ingest runs active")}</span></div>
				<div><b>${d.jobs.filter((j) => j.state === "running").length}</b><span>${__("jobs running")}</span></div>
				<div><b>${d.jobs.filter((j) => j.state === "queued").length}</b><span>${__("jobs waiting")}</span></div>
				<div><b>${d.workers}</b><span>${__("workers")}</span></div>
				<div><b>${d.search.pending || 0}</b><span>${__("search-engine tasks")}</span></div>
				<div>${d.paused ? pill(__("Schedules paused"), "orange") : pill(__("Schedules on"), "green")}</div>
			</div>`;

		const active = d.active_runs.length
			? d.active_runs
					.map(
						(r) => `
				<div class="rdj-run">
					<div class="rdj-run__head">
						${run_link(r)} · <b>${esc(r.profile || "")}</b> ${pill(r.status, r.status === "Running" ? "blue" : "orange")}
						<span class="text-muted">${esc(r.triggered_by || "")} · ${__("started")} ${ago(r.started_on || r.creation)}</span>
						<span class="rdj-run__actions">
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
			: `<p class="text-muted">${__("No ingest is running.")}</p>`;

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
					<td>${j.run ? `<a href="/app/rd-ingest-run/${encodeURIComponent(j.run)}">${esc(j.run)}</a>` : ""}</td>
					<td>${j.items || ""}</td>
					<td class="text-muted small">${ago(j.started_at || j.enqueued_at)}</td>
					<td class="text-right"><button class="btn btn-xs btn-default" data-cancel-job="${esc(j.id)}">${
						j.state === "running" ? __("Stop") : __("Cancel")
					}</button></td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="text-muted">${__("Nothing queued. The workers are idle.")}</p>`;

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
					<td class="text-muted small">${ago(r.finished_on || r.modified)}</td></tr>`
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
			</style>
			${summary}
			<div class="rdj-card"><h4>${__("Ingest runs in progress")}</h4>${active}</div>
			<div class="rdj-card"><h4>${__("Background jobs (Research Desk)")}</h4>${jobs}</div>
			<div class="rdj-card"><h4>${__("Scheduled ingests")}</h4>${schedules}</div>
			<div class="rdj-card"><h4>${__("Search engine")}</h4>${search}</div>
			<div class="rdj-card"><h4>${__("Recent runs")}</h4>${recent}</div>
			<p class="text-muted small">${__("Updated")} ${esc(d.now)} · ${__("refreshes every 5 seconds")}</p>
		`);
	}
}
