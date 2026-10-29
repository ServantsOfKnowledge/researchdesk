// Copyright (c) 2026, Servants of Knowledge and contributors
// License: MIT. See LICENSE
//
// Logs: the errors Research Desk logged (each matched to the release that fixed it), failed background jobs
// (retry them) and the end of any log file. It used to be a card on the Server page.

frappe.pages["resdesk-logs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Logs"), single_column: true });
	wrapper.resdesk_logs = new ResDeskLogs(page);
};

class ResDeskLogs {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="rds"><style>.rds-log { max-height: 520px; overflow:auto; font-size:12px; background: var(--subtle-fg, #f7f7f7); padding:10px; border-radius:6px; white-space: pre-wrap; }</style><div class="rds-logs"></div></div>').appendTo(page.main);
		this.log_view = { source: "errors" };
		this.is_admin = frappe.user.has_role("System Manager") || frappe.user.has_role("SOK Super Admin");
		page.set_secondary_action(__("Refresh"), () => this.load_logs(this.log_view.source, this.log_view.name), "refresh");
		page.add_menu_item(__("Error Log (every entry)"), () => frappe.set_route("List", "Error Log"));
		page.add_menu_item(__("Server"), () => frappe.set_route("resdesk-server"));
		const on = (sel, fn) => this.$body.on("click", sel, (e) => fn($(e.currentTarget), e));
		on("[data-log-source]", ($b) => this.load_logs($b.data("log-source")));
		on("[data-clear-resolved]", () =>
			frappe.confirm(__("Clear the log entries a release has fixed, and the notes of things repaired by themselves? Nothing else is touched."), () =>
				frappe.call({ method: "sok_resdesk.server.clear_resolved_errors", freeze: true, callback: (r) => {
					frappe.show_alert({ message: r.message.message, indicator: "green" });
					this.load_logs("qa");
				} })
			)
		);
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
		this.$body.on("change", "[data-log-file]", (e) => this.load_logs("files", $(e.currentTarget).val()));
		this.load_logs("errors");
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
		const VERDICT = {
			resolved: ["green", (k) => __("Fixed in {0}: safe to ignore", [k.fixed_in])],
			upgrade: ["orange", (k) => __("Fixed in {0}: upgrade to get it", [k.fixed_in])],
			unsure: ["gray", (k) => __("Fixed in {0}: no record of when you upgraded", [k.fixed_in])],
			recurring: ["red", (k) => __("Logged after {0} was installed: needs a look", [k.fixed_in])],
			info: ["blue", () => __("Repaired by itself")],
		};
		const verdict_pill = (k) => (k && VERDICT[k.verdict] ? `<div><span class="indicator-pill ${VERDICT[k.verdict][0]}">${esc(VERDICT[k.verdict][1](k))}</span></div>` : "");
		let body = "";
		if (!this.log_data) body = `<p class="text-muted small">${__("Loading…")}</p>`;
		else if (v.source === "errors")
			body = r.rows.length
				? `<table class="table table-sm small"><tbody>${r.rows
						.map((e) => `<tr><td class="text-muted" style="white-space:nowrap">${esc(String(e.creation).slice(0, 16))}</td><td><a href="/app/error-log/${e.name}">${esc(e.method || e.name)}</a>${verdict_pill(e.known)}<div class="text-muted">${esc(e.error)}</div></td></tr>`)
						.join("")}</tbody></table>`
				: `<p class="text-muted">${__("No errors logged.")}</p>`;
		else if (v.source === "qa")
			body = `<p class="text-muted small">${__("You run {0}. Each entry in the Error Log is matched to the release that fixed it: green is safe to ignore (it happened before the fix was installed), red happened after and needs a look.", [esc(r.installed || "")])}</p>
				${(r.groups || []).length ? `<table class="table table-sm small"><tbody>${r.groups
					.map((g) => `<tr><td>${verdict_pill({ verdict: g.verdict, fixed_in: g.fixed_in })}</td><td><b>${esc(g.title)}</b><div class="text-muted">${esc(g.note)}</div></td><td style="white-space:nowrap">${g.count} ${__("entries")}<div class="text-muted">${__("latest")} ${esc(g.latest)}</div></td></tr>`)
					.join("")}</tbody></table>` : ""}
				${r.unknown && r.unknown.count ? `<div class="alert alert-warning small"><b>${__("{0} entries are not recognised", [r.unknown.count])}</b> (${__("latest")} ${esc(r.unknown.latest)}): ${__("these need a look.")}<br>${r.unknown.examples.map((x) => `<a href="/app/error-log/${esc(x.name)}">${esc(x.method)}</a>`).join(" · ")}</div>` : `<p class="text-muted small">${__("Every entry is a known one.")}</p>`}
				${r.clearable ? `<button class="btn btn-xs btn-primary" data-clear-resolved>${__("Clear the {0} resolved entries", [r.clearable])}</button>` : ""}`;
		else if (v.source === "failed_jobs")
			body = r.rows.length
				? `<table class="table table-sm small"><tbody>${r.rows
						.map((j) => `<tr><td class="text-muted" style="white-space:nowrap">${esc(j.ended_at)}</td><td>${esc(j.method)}<div class="text-muted">${esc(j.error)}</div></td><td>${esc(j.queue)}</td>
							<td><button class="btn btn-xs btn-default" data-retry-job="${esc(j.id)}">${__("Retry")}</button></td></tr>`)
						.join("")}</tbody></table>
					<div style="display:flex;gap:6px"><button class="btn btn-xs btn-primary" data-retry-job="">${__("Retry all")}</button>
					${this.is_admin ? `<button class="btn btn-xs btn-default" data-clear-failed>${__("Clear the list")}</button>` : ""}</div>
					<p class="text-muted small" style="margin-top:6px">${__("Ingest batches that failed go back into their run, which carries on; other jobs simply run again.")}</p>`
				: `<p class="text-muted">${__("No failed jobs.")}</p>`;
		else if (v.source === "files")
			body = `<select class="form-control input-sm" data-log-file style="max-width:320px;margin-bottom:8px">
					<option value="">${__("Choose a log file")}</option>
					${(r.files || []).map((f) => `<option value="${esc(f.name)}" ${f.name === v.name ? "selected" : ""}>${esc(f.name)} (${Math.ceil(f.size / 1024)} KB, ${esc(f.modified)})</option>`).join("")}
				</select>${r.text ? `<pre class="rds-log">${esc(r.text)}</pre>` : ""}`;
		$box.html(`<div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap">
			${tab("errors", __("Errors"))}${tab("qa", __("Log QA"))}${tab("failed_jobs", __("Failed jobs"))}${tab("files", __("Log files"))}
		</div>${body}`);
		const pre = $box.find(".rds-log")[0];
		if (pre) pre.scrollTop = pre.scrollHeight;
	}
}
