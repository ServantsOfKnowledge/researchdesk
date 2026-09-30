"""See and control Research Desk background work: ingest runs, queued jobs, schedules, search tasks.

Used by the Desk page /app/resdesk-jobs and by `bench resdesk jobs`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

MANAGERS = ("System Manager", "ResDesk Manager")
ACTIVE = ("Queued", "Running")

# what our background jobs are, in plain words
KINDS = {
	"sok_resdesk.ingest.plan_run": "Ingest: listing books",
	"sok_resdesk.ingest.run_batch": "Ingest: batch of books",
	"sok_resdesk.search.rebuild_batch": "Search index rebuild",
	"sok_resdesk.access.apply_visibility": "Change who can see books",
	"sok_resdesk.access.recompute": "Apply access rules",
	"sok_resdesk.curation.add_items": "Add books to a collection",
	"sok_resdesk.curation.remove_items": "Remove books from a collection",
	"sok_resdesk.curation.apply_rules_now": "Apply collection rules",
	"sok_resdesk.transfer.run_export": "Metadata export",
	"sok_resdesk.transfer.apply_plan": "Spreadsheet import",
	"sok_resdesk.outbound.run": "Push metadata to another system",
	"sok_resdesk.outbound.auto_push": "Automatic push of one book",
}


# -- reading ----------------------------------------------------------------------------------

def _local(value) -> str:
	"""RQ stores UTC; show times in the site's time zone like the rest of the Desk."""
	if not value:
		return ""
	from frappe.utils import convert_utc_to_system_timezone

	return str(convert_utc_to_system_timezone(value).replace(tzinfo=None))[:19]


def _rq_jobs() -> list[dict]:
	"""Queued and running RQ jobs of this site that belong to Research Desk."""
	from frappe.utils.background_jobs import get_queues, get_redis_conn
	from rq.job import Job
	from rq.registry import StartedJobRegistry

	conn = get_redis_conn()
	prefix = f"{frappe.local.site}||"
	out = []
	for queue in get_queues(connection=conn):
		ids = [(i, "queued") for i in queue.get_job_ids()]
		ids += [(i, "running") for i in StartedJobRegistry(queue=queue).get_job_ids()]
		for job_id, state in ids:
			if not job_id.startswith(prefix) and "sok_resdesk" not in job_id:
				continue
			try:
				job = Job.fetch(job_id, connection=conn)
			except Exception:
				continue
			kw = job.kwargs or {}
			if kw.get("site") not in (None, frappe.local.site):
				continue
			method = kw.get("job_name") or kw.get("method") or job.func_name or ""
			method = method if isinstance(method, str) else getattr(method, "__name__", str(method))
			if "sok_resdesk" not in method:
				continue
			args = kw.get("kwargs") or {}
			out.append({
				"id": job_id,
				"short_id": job_id.split("||", 1)[-1],
				"state": state,
				"queue": queue.name.split(":")[-1],
				"kind": KINDS.get(method, method.rsplit(".", 1)[-1]),
				"method": method,
				"run": args.get("run_name"),
				"items": len(args.get("item_ids") or args.get("names") or []) or None,
				"enqueued_at": _local(job.enqueued_at),
				"started_at": _local(job.started_at),
			})
	out.sort(key=lambda j: (j["state"] != "running", j["enqueued_at"]))
	return out


def _search_tasks() -> dict:
	from sok_resdesk.search import MeiliClient, SearchError

	try:
		client = MeiliClient.from_settings()
		res = client._req("GET", "/tasks", params={"statuses": "enqueued,processing", "limit": 50})
		tasks = res.get("results", [])
		return {
			"ok": True,
			"pending": res.get("total", len(tasks)),
			"processing": sum(1 for t in tasks if t.get("status") == "processing"),
			"tasks": [{"uid": t.get("uid"), "index": t.get("indexUid"), "type": t.get("type"),
					   "status": t.get("status"), "enqueued_at": (t.get("enqueuedAt") or "")[:19]}
					  for t in tasks[:10]],
		}
	except SearchError as e:
		return {"ok": False, "error": str(e)[:200], "pending": 0, "tasks": []}


def _workers() -> int:
	try:
		from frappe.utils.background_jobs import get_workers

		return len(get_workers())
	except Exception:
		return 0


@frappe.whitelist()
def overview() -> dict:
	frappe.only_for(MANAGERS)
	fields = ["name", "profile", "status", "triggered_by", "total_found", "processed", "created_count",
			  "updated_count", "skipped_count", "failed_count", "chunks_total", "pending_chunks",
			  "started_on", "finished_on", "creation", "modified"]
	active = frappe.get_all("RD Ingest Run", filters={"status": ("in", ACTIVE)}, fields=fields, order_by="creation desc")
	recent = frappe.get_all("RD Ingest Run", filters={"status": ("not in", ACTIVE)}, fields=fields,
							order_by="creation desc", limit=10)
	schedules = frappe.get_all("RD Ingest Profile", filters={"enabled": 1, "schedule": ("in", ["Hourly", "Daily", "Weekly"])},
							   fields=["name", "schedule", "last_run_on", "last_status"], order_by="name")
	try:
		jobs = _rq_jobs()
		jobs_error = None
	except Exception as e:
		jobs, jobs_error = [], str(e)[:200]
	return {
		"now": str(now_datetime())[:19],
		"paused": cint(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest")),
		"workers": _workers(),
		"active_runs": active,
		"recent_runs": recent,
		"jobs": jobs,
		"jobs_error": jobs_error,
		"schedules": schedules,
		"search": _search_tasks(),
	}


# -- controlling --------------------------------------------------------------------------------

def _stop_rq(job_id: str, force: bool) -> str:
	"""Cancel a queued job, or (force) stop a running one. Returns what happened."""
	from frappe.utils.background_jobs import get_redis_conn
	from rq.command import send_stop_job_command
	from rq.job import Job

	conn = get_redis_conn()
	try:
		job = Job.fetch(job_id, connection=conn)
	except Exception:
		return "gone"
	status = job.get_status(refresh=True)
	status = getattr(status, "value", status)
	if status in ("queued", "deferred", "scheduled"):
		job.cancel()
		job.delete()
		return "cancelled"
	if status == "started" and force:
		try:
			send_stop_job_command(connection=conn, job_id=job_id)
			return "stopped"
		except Exception:
			return "not running"
	return status


def _cancel_run_row(run: str, note: str) -> None:
	frappe.db.sql(
		"update `tabRD Ingest Run` set status='Cancelled', finished_on=%s, "
		"log = right(concat(ifnull(log,''), %s), 200000) where name=%s and status in ('Queued','Running')",
		(now_datetime(), f"{now_datetime().strftime('%H:%M:%S')} {note}\n", run),
	)
	profile = frappe.db.get_value("RD Ingest Run", run, "profile")
	if profile:
		frappe.db.set_value("RD Ingest Profile", profile, "last_status", "Cancelled", update_modified=False)


@frappe.whitelist()
def stop_run(run: str, force: int = 0) -> dict:
	"""Stop one ingest run: mark it cancelled and drop its queued batches.

	Running batches stop after the book they are on (a few seconds). With force=1 they are
	killed at once; the book in progress is rolled back and simply ingested again next time.
	"""
	frappe.only_for(MANAGERS)
	who = frappe.session.user
	_cancel_run_row(run, f"Stopped by {who}" + (" (immediately)" if cint(force) else ""))
	frappe.db.commit()
	done = {"cancelled": 0, "stopped": 0}
	for job in _rq_jobs():
		if job["run"] == run or job["short_id"] in (f"resdesk-plan-{run}",) or job["short_id"].startswith(f"resdesk-{run}-"):
			result = _stop_rq(job["id"], bool(cint(force)))
			if result in done:
				done[result] += 1
	return {"message": _("Run {0} stopped: {1} queued batches removed, {2} running batches stopped.")
			.format(run, done["cancelled"], done["stopped"]), **done}


@frappe.whitelist()
def cancel_job(job_id: str, force: int = 1) -> dict:
	"""Cancel one queued Research Desk job, or stop it if it is running."""
	frappe.only_for(MANAGERS)
	if not any(j["id"] == job_id for j in _rq_jobs()):
		frappe.throw(_("That job is not a Research Desk job, or it has already finished."))
	result = _stop_rq(job_id, bool(cint(force)))
	return {"result": result, "message": _("Job {0}: {1}").format(job_id.split("||")[-1], _(result))}


@frappe.whitelist()
def set_paused(paused: int = 1) -> dict:
	"""Pause or resume scheduled (Hourly/Daily/Weekly) ingests. Manual runs still work."""
	frappe.only_for(MANAGERS)
	frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 1 if cint(paused) else 0)
	frappe.db.commit()
	return {"paused": cint(paused), "message": _("Scheduled ingests paused.") if cint(paused)
			else _("Scheduled ingests resumed.")}


@frappe.whitelist()
def cancel_search_tasks() -> dict:
	"""Cancel Meilisearch indexing work that hasn't finished. The books stay in the catalogue;
	run a re-index later to make their text searchable again."""
	frappe.only_for(MANAGERS)
	from sok_resdesk.search import MeiliClient

	client = MeiliClient.from_settings()
	client._req("POST", "/tasks/cancel", params={"statuses": "enqueued,processing"})
	return {"message": _("Pending search-engine tasks cancelled. Run Rebuild Search Index later if search results look incomplete.")}


@frappe.whitelist()
def stop_all(force: int = 0, pause: int = 1, search: int = 0) -> dict:
	"""Stop every Research Desk background activity.

	Cancels all active ingest runs, removes every queued Research Desk job (ingest batches,
	re-index batches, visibility changes), optionally pauses schedules, force-stops running
	jobs and cancels pending search-engine tasks.
	"""
	frappe.only_for(MANAGERS)
	runs = frappe.get_all("RD Ingest Run", filters={"status": ("in", ACTIVE)}, pluck="name")
	for run in runs:
		_cancel_run_row(run, f"Stopped by {frappe.session.user} (stop everything)")
	frappe.db.sql("update `tabRD Push Run` set status='Cancelled' where status in ('Queued','Running')")
	if cint(pause):
		frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 1)
	frappe.db.commit()
	# re-index batches check this between books and stop (queued ones are removed below)
	frappe.cache.set_value("resdesk:stop-background", 1, expires_in_sec=600)
	counts = {"cancelled": 0, "stopped": 0}
	for job in _rq_jobs():
		result = _stop_rq(job["id"], bool(cint(force)))
		if result in counts:
			counts[result] += 1
	if cint(search):
		try:
			cancel_search_tasks()
		except Exception:
			pass
	parts = [_("{0} runs cancelled").format(len(runs)), _("{0} queued jobs removed").format(counts["cancelled"])]
	if cint(force):
		parts.append(_("{0} running jobs stopped").format(counts["stopped"]))
	if cint(pause):
		parts.append(_("schedules paused"))
	return {"runs": len(runs), **counts, "message": ", ".join(parts) + "."}
