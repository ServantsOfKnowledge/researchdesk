"""See and control Research Desk background work: ingest runs, queued jobs, schedules, search tasks.

Used by the Desk page /app/resdesk-jobs and by `bench resdesk jobs`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import holding

MANAGERS = ("System Manager", "ResDesk Manager")
ACTIVE = ("Queued", "Running", "Paused")

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
			out.append(
				{
					"id": job_id,
					"short_id": job_id.split("||", 1)[-1],
					"timeout": job.timeout if isinstance(job.timeout, int) else None,
					"args": args,
					"state": state,
					"queue": queue.name.split(":")[-1],
					"kind": KINDS.get(method, method.rsplit(".", 1)[-1]),
					"method": method,
					"run": args.get("run_name"),
					"items": len(args.get("item_ids") or args.get("names") or []) or None,
					"enqueued_at": _local(job.enqueued_at),
					"started_at": _local(job.started_at),
				}
			)
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
			"tasks": [
				{
					"uid": t.get("uid"),
					"index": t.get("indexUid"),
					"type": t.get("type"),
					"status": t.get("status"),
					"enqueued_at": (t.get("enqueuedAt") or "")[:19],
				}
				for t in tasks[:10]
			],
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
	from sok_resdesk.guide import mark_visited

	mark_visited("jobs")  # ticks "Watch the ingest" on the getting-started checklist
	fields = [
		"name",
		"profile",
		"status",
		"triggered_by",
		"total_found",
		"processed",
		"created_count",
		"updated_count",
		"skipped_count",
		"failed_count",
		"chunks_total",
		"pending_chunks",
		"started_on",
		"finished_on",
		"creation",
		"modified",
	]
	active = frappe.get_all(
		"RD Ingest Run", filters={"status": ("in", ACTIVE)}, fields=fields, order_by="creation desc"
	)
	recent = frappe.get_all(
		"RD Ingest Run",
		filters={"status": ("not in", ACTIVE)},
		fields=fields,
		order_by="creation desc",
		limit=10,
	)
	schedules = frappe.get_all(
		"RD Ingest Profile",
		filters={"enabled": 1, "schedule": ("in", ["Hourly", "Daily", "Weekly"])},
		fields=["name", "schedule", "last_run_on", "last_status"],
		order_by="name",
	)
	try:
		jobs = _rq_jobs()
		for j in jobs:
			j.pop("args", None)
		jobs_error = None
	except Exception as e:
		jobs, jobs_error = [], str(e)[:200]
	push_fields = [
		"name",
		"target",
		"status",
		"dry_run",
		"triggered_by",
		"total",
		"sent",
		"unchanged",
		"skipped",
		"failed",
		"creation",
		"modified",
	]
	return {
		"now": str(now_datetime())[:19],
		"paused": cint(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest")),
		"paused_all": int(holding.is_paused()),
		"quiet": quiet_status(),
		"machine": machine(),
		"held": [
			{
				"key": h.get("key"),
				"kind": h.get("kind") or KINDS.get(h["method"], h["method"]),
				"held_on": h.get("held_on"),
				"job_id": h.get("job_id"),
				"run": (h.get("kwargs") or {}).get("run_name"),
			}
			for h in holding.held_jobs()
		],
		"push_runs": frappe.get_all(
			"RD Push Run", filters={"status": ("in", ACTIVE)}, fields=push_fields, order_by="creation desc"
		),
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
		"held_work=null, waiting_work=null, log = right(concat(ifnull(log,''), %s), 200000) "
		"where name=%s and status in ('Queued','Running','Paused')",
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
		if (
			job["run"] == run
			or job["short_id"] in (f"resdesk-plan-{run}",)
			or job["short_id"].startswith(f"resdesk-{run}-")
		):
			result = _stop_rq(job["id"], bool(cint(force)))
			if result in done:
				done[result] += 1
	return {
		"message": _("Run {0} stopped: {1} queued batches removed, {2} running batches stopped.").format(
			run, done["cancelled"], done["stopped"]
		),
		**done,
	}


@frappe.whitelist()
def cancel_job(job_id: str, force: int = 1) -> dict:
	"""Cancel one queued Research Desk job, or stop it if it is running."""
	frappe.only_for(MANAGERS)
	if not any(j["id"] == job_id for j in _rq_jobs()):
		frappe.throw(_("That job is not a Research Desk job, or it has already finished."))
	result = _stop_rq(job_id, bool(cint(force)))
	return {"result": result, "message": _("Job {0}: {1}").format(job_id.split("||")[-1], _(result))}


# -- trying again ----------------------------------------------------------------------------


def _failed_registry_jobs() -> list[tuple]:
	"""(registry, job_id, job) for every failed RQ job of this site."""
	from frappe.utils.background_jobs import get_queues, get_redis_conn
	from rq.job import Job
	from rq.registry import FailedJobRegistry

	conn = get_redis_conn()
	out = []
	# get_queues: the queues under their real names (Frappe prefixes them with the bench's)
	for queue in get_queues(connection=conn):
		registry = FailedJobRegistry(queue=queue)
		for job_id in registry.get_job_ids():
			try:
				job = Job.fetch(job_id, connection=conn)
			except Exception:
				registry.remove(job_id)  # its data expired: nothing left to retry
				continue
			if (job.kwargs or {}).get("site") not in (None, frappe.local.site):
				continue
			out.append((registry, job_id, job))
	return out


def _job_method(job) -> str:
	kw = job.kwargs or {}
	method = kw.get("job_name") or kw.get("method") or job.func_name or ""
	return method if isinstance(method, str) else getattr(method, "__name__", str(method))


def _job_run(job) -> str | None:
	"""The ingest run a failed job belonged to, if it was an ingest job."""
	if _job_method(job).endswith(("ingest.run_batch", "ingest.plan_run")):
		return ((job.kwargs or {}).get("kwargs") or {}).get("run_name")
	return None


def _failed_books(run) -> list:
	"""The books that failed in a run: recorded one per line (since 0.17.1), or read back from
	the FAIL lines of older runs' logs."""
	import json
	import re

	books, seen = [], set()
	for line in (run.get("failed_items") or "").splitlines():
		try:
			entry = json.loads(line)
		except ValueError:
			continue
		key = entry[0] if isinstance(entry, list) else entry
		if key not in seen:
			seen.add(key)
			books.append(entry)
	if not books and not run.get("failed_items"):
		for item_id in re.findall(r"^\S* ?FAIL (\S+?):", run.log or "", re.M):
			if item_id not in seen:
				seen.add(item_id)
				books.append(item_id)
	return books


@frappe.whitelist()
def retry_run(run: str) -> dict:
	"""Try again what went wrong in an ingest run, in the same run:

	* a run that failed, was interrupted or stopped, or left books out at the book limit lists
	  its books again and takes only those not done yet (books ingested since the run started,
	  by it or by any other run, are skipped);
	* otherwise (Completed with Errors) batches that failed as a whole are put back in the
	  queue and books that failed one by one are taken again, in new batches.
	"""
	frappe.only_for(MANAGERS)
	from sok_resdesk.ingest import RUN, _feed, add_waiting, enqueue_plan, waiting_batches

	doc = frappe.get_doc("RD Ingest Run", run)
	if doc.status in ACTIVE:
		frappe.throw(_("Run {0} is still {1}: wait for it, or stop it first.").format(run, _(doc.status)))
	who = frappe.session.user
	stamp = now_datetime().strftime("%H:%M:%S")

	failed_jobs = [(reg, jid, job) for reg, jid, job in _failed_registry_jobs() if _job_run(job) == run]
	plan_failed = any(_job_method(job).endswith("plan_run") for _r, _jid, job in failed_jobs)
	books = _failed_books(doc)
	if books and not all(isinstance(b, list) for b in books):
		# identifiers read back from an older run's log: fine for archive.org, but a folder
		# source needs each book's folder too, so such a run lists its folders again instead
		profile = frappe.get_doc("RD Ingest Profile", doc.profile) if doc.profile else None
		if profile and profile.is_folder:
			books = []
			if doc.status == "Completed with Errors":
				frappe.db.set_value("RD Ingest Run", run, "status", "Interrupted", update_modified=False)
				doc.status = "Interrupted"

	left_out = cint(doc.get("limit_skipped")) and not failed_jobs and not books
	if left_out:
		from sok_resdesk.capacity import has_room

		if not has_room():
			frappe.throw(
				_(
					"The book limit is still reached, so the {0} books left out can't come in yet. Raise it in Settings → Machine Resources → Book Limit first."
				).format(cint(doc.limit_skipped))
			)
	if (
		doc.status == "Failed"
		or plan_failed
		# cut off or stopped: list the books again and skip those already done (whatever was
		# queued, cut off or never queued is picked up, and nothing is fetched twice)
		or doc.status in ("Interrupted", "Cancelled")
		or left_out
	):
		other = frappe.db.get_value(
			"RD Ingest Run",
			{
				"profile": doc.profile,
				"name": ("!=", run),
				"status": ("in", ["Queued", "Running", "Paused"]),
			},
			"name",
		)
		if other:
			frappe.throw(
				_("Run {0} of the same profile is going: let it finish first, or stop it.").format(other)
			)
		for reg, jid, _job in failed_jobs:
			reg.remove(jid, delete_job=True)
		frappe.db.sql(
			f"update `{RUN}` set status='Queued', finished_on=null, failed_items=null, waiting_work=null, pending_chunks=0, failed_count=0, "
			"log = right(concat(ifnull(log,''), %s), 200000) where name=%s",
			(
				f"{stamp} Started again by {who}: listing the books again (those already done are skipped)\n",
				run,
			),
		)
		frappe.db.commit()
		enqueue_plan(run)
		return {
			"message": _(
				"Run {0} starts again: it lists the books again and skips those already done."
			).format(run)
		}

	if not failed_jobs and not books:
		return {"message": _("Nothing in run {0} failed, so there is nothing to try again.").format(run)}

	for reg, jid, _job in failed_jobs:
		reg.requeue(jid)
	size = max(1, cint(frappe.db.get_single_value("RD Settings", "batch_size")) or 50)
	batches = [books[i : i + size] for i in range(0, len(books), size)]
	start = cint(doc.chunks_total)
	waiting = len(waiting_batches(run))
	frappe.db.sql(
		f"""update `{RUN}` set status='Running', finished_on=null, failed_items=null,
		failed_count = greatest(ifnull(failed_count,0) - %s, 0),
		processed = greatest(ifnull(processed,0) - %s, 0),
		pending_chunks = %s, chunks_total = ifnull(chunks_total,0) + %s,
		log = right(concat(ifnull(log,''), %s), 200000) where name=%s""",
		(
			len(books),
			len(books),
			waiting + len(failed_jobs) + len(batches),
			len(batches),
			f"{stamp} Retry by {who}: {len(failed_jobs)} failed batch(es) back in the queue, "
			f"{len(books)} book(s) that failed taken again\n",
			run,
		),
	)
	if batches:
		add_waiting(run, batches, next_no=start + 1)
	frappe.db.commit()
	if batches:
		_feed(run)
	profile = doc.profile
	if profile:
		frappe.db.set_value("RD Ingest Profile", profile, "last_status", "Running", update_modified=False)
	return {
		"message": _("Trying again in run {0}: {1} book(s) and {2} batch(es).").format(
			run, len(books), len(failed_jobs)
		),
		"books": len(books),
		"batches": len(failed_jobs),
	}


@frappe.whitelist()
def retry_failed_jobs(job_id: str | None = None) -> dict:
	"""Server page → Logs → Failed jobs: try one failed background job again, or all of them.
	Ingest jobs go through retry_run, so their run carries on properly."""
	frappe.only_for(MANAGERS)
	runs, plain = set(), 0
	for reg, jid, job in _failed_registry_jobs():
		if job_id and jid.split("||")[-1] != job_id.split("||")[-1]:
			continue
		run = _job_run(job)
		if run and frappe.db.exists("RD Ingest Run", run):
			runs.add(run)
			continue
		reg.requeue(jid)
		plain += 1
	messages = []
	for run in sorted(runs):
		if frappe.db.get_value("RD Ingest Run", run, "status") in ACTIVE:
			# the run is still going: only its failed batches go back (the run still counts them)
			back = 0
			for reg, jid, job in _failed_registry_jobs():
				if _job_run(job) == run and (not job_id or jid.split("||")[-1] == job_id.split("||")[-1]):
					reg.requeue(jid)
					back += 1
			messages.append(_("Run {0}: {1} failed batch(es) back in the queue.").format(run, back))
		else:
			messages.append(retry_run(run)["message"])
	if plain:
		messages.append(_("{0} other job(s) back in the queue.").format(plain))
	return {
		"message": " ".join(messages) or _("No failed jobs to try again."),
		"runs": sorted(runs),
		"jobs": plain,
	}


@frappe.whitelist()
def clear_failed_jobs() -> dict:
	"""Forget every failed background job of this site (the list on the Server page)."""
	frappe.only_for(("System Manager",))
	n = 0
	for reg, jid, _job in _failed_registry_jobs():
		reg.remove(jid, delete_job=True)
		n += 1
	return {"message": _("{0} failed job(s) cleared.").format(n), "cleared": n}


@frappe.whitelist()
def set_paused(paused: int = 1) -> dict:
	"""Pause or resume scheduled (Hourly/Daily/Weekly) ingests. Manual runs still work."""
	frappe.only_for(MANAGERS)
	frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 1 if cint(paused) else 0)
	frappe.db.commit()
	return {
		"paused": cint(paused),
		"message": _("Scheduled ingests paused.") if cint(paused) else _("Scheduled ingests resumed."),
	}


@frappe.whitelist()
def cancel_search_tasks() -> dict:
	"""Cancel Meilisearch indexing work that hasn't finished. The books stay in the catalogue;
	run a re-index later to make their text searchable again."""
	frappe.only_for(MANAGERS)
	from sok_resdesk.search import MeiliClient

	client = MeiliClient.from_settings()
	client._req("POST", "/tasks/cancel", params={"statuses": "enqueued,processing"})
	return {
		"message": _(
			"Pending search-engine tasks cancelled. Run Rebuild Search Index later if search results look incomplete."
		)
	}


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
	frappe.db.sql(
		"update `tabRD Push Run` set status='Cancelled', held_items=null, finished_on=%s "
		"where status in ('Queued','Running','Paused')",
		now_datetime(),
	)
	dropped = holding.release(discard=True)  # held jobs are dropped too, and Pause All ends
	frappe.db.set_single_value("RD Settings", "pause_background", 0)
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
			frappe.log_error(title="Research Desk: could not cancel search-engine tasks")
	parts = [
		_("{0} runs cancelled").format(len(runs)),
		_("{0} queued jobs removed").format(counts["cancelled"] + dropped),
	]
	if cint(force):
		parts.append(_("{0} running jobs stopped").format(counts["stopped"]))
	if cint(pause):
		parts.append(_("schedules paused"))
	return {"runs": len(runs), **counts, "message": ", ".join(parts) + "."}


# -- pausing ------------------------------------------------------------------------------------
#
# Pause keeps work instead of throwing it away. An ingest run keeps the books it hasn't done on
# the run (held_work) and Resume queues them again; running batches stop after their current
# book. Other jobs are held in RD Settings (see holding.py) and put back in the queue on Resume.


def _run_jobs(run: str) -> list[dict]:
	return [
		j
		for j in _rq_jobs()
		if j["run"] == run
		or j["short_id"] == f"resdesk-plan-{run}"
		or j["short_id"].startswith(f"resdesk-{run}-")
	]


def _pause_ingest(run: str, who: str) -> bool:
	from sok_resdesk.ingest import _log, _status, hold_work, take_waiting

	if _status(run, lock=True) not in ("Queued", "Running"):
		frappe.db.rollback()
		return False
	frappe.db.sql("update `tabRD Ingest Run` set status='Paused' where name=%s", run)
	frappe.db.commit()
	items, plan, batches = [], False, 0
	for j in _run_jobs(run):
		if j["state"] != "queued" or _stop_rq(j["id"], False) != "cancelled":
			continue  # running batches notice the pause after their current book
		if j["method"].endswith("plan_run"):
			plan = True
		else:
			items += j["args"].get("item_ids") or []
			batches += 1
	_status(run, lock=True)
	waiting = take_waiting(run)  # batches not yet queued are kept too
	for batch in waiting:
		items += batch
	batches += len(waiting)
	hold_work(run, items, plan=plan)
	frappe.db.sql(
		"update `tabRD Ingest Run` set pending_chunks=greatest(ifnull(pending_chunks,0)-%s,0) where name=%s",
		(batches, run),
	)
	frappe.db.commit()
	_log(
		run,
		f"Paused by {who}: {len(items)} queued books kept" + (", listing not started yet" if plan else ""),
	)
	frappe.db.set_value(
		"RD Ingest Profile",
		frappe.db.get_value("RD Ingest Run", run, "profile"),
		"last_status",
		"Paused",
		update_modified=False,
	)
	frappe.db.commit()
	return True


def _resume_ingest(run: str, who: str) -> int:
	import json

	from sok_resdesk.catalogue import settings
	from sok_resdesk.ingest import _feed, _finish, _log, _status, add_waiting, enqueue_plan

	if _status(run, lock=True) != "Paused":
		frappe.db.rollback()
		return -1
	raw = frappe.db.get_value("RD Ingest Run", run, "held_work")
	held = json.loads(raw) if raw else {}
	items = held.get("items") or []
	size = max(1, cint(settings().get("batch_size")) or 50)
	batches = [items[i : i + size] for i in range(0, len(items), size)]
	frappe.db.sql(
		"update `tabRD Ingest Run` set status=%s, held_work=null, pending_chunks=ifnull(pending_chunks,0)+%s, "
		"chunks_total=ifnull(chunks_total,0)+%s where name=%s",
		("Queued" if held.get("plan") else "Running", len(batches), len(batches), run),
	)
	frappe.db.commit()
	_log(
		run,
		f"Resumed by {who}: {len(items)} books queued again"
		+ (", listing restarted" if held.get("plan") else ""),
	)
	frappe.db.set_value(
		"RD Ingest Profile",
		frappe.db.get_value("RD Ingest Run", run, "profile"),
		"last_status",
		"Running",
		update_modified=False,
	)
	frappe.db.commit()
	if held.get("plan"):
		enqueue_plan(run)
	if batches:
		add_waiting(run, batches)
		frappe.db.commit()
		_feed(run)
	if (
		not held.get("plan")
		and not batches
		and not cint(frappe.db.get_value("RD Ingest Run", run, "pending_chunks"))
	):
		_finish(run)
	frappe.db.commit()
	return len(items)


@frappe.whitelist()
def pause_run(run: str) -> dict:
	"""Pause an ingest or push run. Nothing is lost: Resume carries on where it stopped."""
	frappe.only_for(MANAGERS)
	who = frappe.session.user
	if run.startswith("PUSH-") or frappe.db.exists("RD Push Run", run):
		from sok_resdesk.outbound import pause_push

		ok = pause_push(run, who)
	else:
		ok = _pause_ingest(run, who)
	if not ok:
		frappe.throw(_("Run {0} is not running or queued, so it can't be paused.").format(run))
	return {
		"message": _(
			"Run {0} paused. Running batches stop after the book they are on; press Resume to carry on."
		).format(run)
	}


@frappe.whitelist()
def resume_run(run: str) -> dict:
	frappe.only_for(MANAGERS)
	if holding.is_paused():
		frappe.throw(_("Pause All is on. Press Resume All to carry on with everything."))
	who = frappe.session.user
	if run.startswith("PUSH-") or frappe.db.exists("RD Push Run", run):
		from sok_resdesk.outbound import resume_push

		n = resume_push(run, who)
	else:
		n = _resume_ingest(run, who)
	if n < 0:
		frappe.throw(_("Run {0} is not paused.").format(run))
	return {"message": _("Run {0} resumed.").format(run)}


@frappe.whitelist()
def hold_job(job_id: str) -> dict:
	"""Take one queued job out of the queue and keep it (Held jobs) instead of cancelling it."""
	frappe.only_for(MANAGERS)
	job = next((j for j in _rq_jobs() if j["id"] == job_id), None)
	if not job:
		frappe.throw(_("That job is not a Research Desk job, or it has already finished."))
	if job["state"] != "queued":
		frappe.throw(_("Only waiting jobs can be held. Pause its run instead, or stop the job."))
	if _stop_rq(job_id, False) != "cancelled":
		frappe.throw(_("The job started just now; it can't be held any more."))
	holding.hold(
		job["method"],
		job["args"],
		queue=job["queue"],
		timeout=job["timeout"],
		job_id=job["short_id"],
		kind=job["kind"],
	)
	return {"message": _("Job held. Release it from Held jobs when you want it to run.")}


@frappe.whitelist()
def release_held(keys=None, discard: int = 0) -> dict:
	"""Put held jobs back in the queue (all when keys is empty), or discard them."""
	frappe.only_for(MANAGERS)
	keys = frappe.parse_json(keys) if isinstance(keys, str) and keys else keys
	if not cint(discard) and holding.is_paused():
		frappe.throw(_("Pause All is on. Press Resume All to carry on with everything."))
	n = holding.release(list(keys) if keys else None, discard=bool(cint(discard)))
	return {
		"message": (
			_("{0} held jobs discarded.") if cint(discard) else _("{0} held jobs queued again.")
		).format(n)
	}


@frappe.whitelist()
def pause_all() -> dict:
	"""Pause everything: runs are paused, waiting jobs held, schedules paused, and new jobs wait."""
	frappe.only_for(MANAGERS)
	runs, held = _pause_all(frappe.session.user)
	return {
		"message": _(
			"Paused: {0} runs, {1} waiting jobs held, schedules paused. Jobs already running finish "
			"their current step (a few seconds). Press Resume All to carry on."
		).format(runs, held)
	}


@frappe.whitelist()
def resume_all() -> dict:
	frappe.only_for(MANAGERS)
	runs, n = _resume_all(frappe.session.user)
	return {"message": _("Resumed: {0} runs and {1} held jobs are running again.").format(runs, n)}


def _pause_all(who: str) -> tuple[int, int]:
	schedules_were = cint(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest"))
	frappe.db.set_single_value("RD Settings", "pause_background", 1)
	frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 1)
	frappe.db.set_default("resdesk_schedules_were_paused", str(schedules_were))
	frappe.db.commit()
	runs = sum(
		_pause_ingest(r, who)
		for r in frappe.get_all(
			"RD Ingest Run", filters={"status": ("in", ["Queued", "Running"])}, pluck="name"
		)
	)
	from sok_resdesk.outbound import pause_push

	runs += sum(
		pause_push(r, who)
		for r in frappe.get_all(
			"RD Push Run", filters={"status": ("in", ["Queued", "Running"])}, pluck="name"
		)
	)
	held = 0
	for j in _rq_jobs():
		if j["state"] == "queued" and _stop_rq(j["id"], False) == "cancelled":
			holding.hold(
				j["method"],
				j["args"],
				queue=j["queue"],
				timeout=j["timeout"],
				job_id=j["short_id"],
				kind=j["kind"],
			)
			held += 1
	return runs, held


def _resume_all(who: str) -> tuple[int, int]:
	frappe.db.set_single_value("RD Settings", "pause_background", 0)
	was = frappe.db.get_default("resdesk_schedules_were_paused")
	frappe.db.set_single_value(
		"RD Settings", "pause_scheduled_ingest", cint(was) if was not in (None, "") else 0
	)
	frappe.db.set_default("resdesk_schedules_were_paused", "")
	frappe.db.commit()
	from sok_resdesk.outbound import resume_push

	runs = 0
	for r in frappe.get_all("RD Ingest Run", filters={"status": "Paused"}, pluck="name"):
		runs += _resume_ingest(r, who) >= 0
	for r in frappe.get_all("RD Push Run", filters={"status": "Paused"}, pluck="name"):
		runs += resume_push(r, who) >= 0
	n = holding.release()
	return runs, n


# -- the machine: how busy it is, and the caps Research Desk runs under ---------------------------


def _limits() -> dict:
	import os

	raw = os.environ.get("RESDESK_RESOURCES", "")
	return dict(kv.split("=", 1) for kv in raw.split(";") if "=" in kv)


def _host() -> dict:
	"""CPU load and memory of the machine the containers run on (inside Docker Desktop: its VM)."""
	import os
	import shutil

	out = {"cpus": os.cpu_count() or 0}
	try:
		out["load"] = [round(x, 2) for x in os.getloadavg()]
	except OSError:
		out["load"] = []
	try:
		info = {}
		with open("/proc/meminfo") as f:
			for line in f:
				k, v = line.split(":", 1)
				info[k] = int(v.split()[0]) * 1024
		out["mem_total"], out["mem_available"] = info.get("MemTotal"), info.get("MemAvailable")
	except OSError:
		pass
	try:
		du = shutil.disk_usage(frappe.get_site_path())
		out["disk_total"], out["disk_free"] = du.total, du.free
	except OSError:
		pass
	return out


def _containers() -> list[dict] | None:
	"""CPU % and memory of each Research Desk container, through the optional read-only
	Docker proxy (./resdesk.sh resources monitor on). None when it isn't running."""
	import os
	from concurrent.futures import ThreadPoolExecutor

	import requests

	api = os.environ.get("RESDESK_DOCKER_API")
	if not api:
		return None
	cached = frappe.cache.get_value("resdesk:container-stats")
	if cached is not None:
		return cached
	try:
		flt = frappe.as_json({"label": ["com.docker.compose.project=sok-resdesk"], "status": ["running"]})
		items = requests.get(f"{api}/containers/json", params={"filters": flt}, timeout=3).json()
	except Exception:
		return None

	previous = frappe.cache.get_value("resdesk:container-cpu") or {}
	current = {}

	def one(c):
		# one-shot = a single fast sample; CPU % comes from the difference with the last one
		try:
			st = requests.get(
				f"{api}/containers/{c['Id']}/stats", params={"stream": "false", "one-shot": "true"}, timeout=4
			).json()
			cpu = st["cpu_stats"]
			total, system = cpu["cpu_usage"]["total_usage"], cpu.get("system_cpu_usage", 0)
			ncpu = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage") or [1])
			current[c["Id"]] = (total, system)
			before = previous.get(c["Id"])
			pct = 0.0
			if before and system > before[1]:
				pct = round((total - before[0]) / (system - before[1]) * ncpu * 100, 1)
			mem = st.get("memory_stats", {})
			used = mem.get("usage", 0) - (mem.get("stats", {}).get("inactive_file") or 0)
			return {
				"name": c["Labels"].get("com.docker.compose.service", c["Names"][0].strip("/")),
				"number": c["Labels"].get("com.docker.compose.container-number", "1"),
				"cpu": max(pct, 0.0),
				"mem": used,
				"mem_limit": mem.get("limit", 0),
			}
		except Exception:
			return None

	with ThreadPoolExecutor(max_workers=8) as pool:
		rows = [r for r in pool.map(one, items) if r]
	rows.sort(key=lambda r: (-r["cpu"], r["name"]))
	frappe.cache.set_value("resdesk:container-cpu", current, expires_in_sec=600)
	frappe.cache.set_value("resdesk:container-stats", rows, expires_in_sec=4)
	return rows


def _search_size() -> int | None:
	from sok_resdesk.search import MeiliClient

	try:
		return MeiliClient.from_settings()._req("GET", "/stats").get("databaseSize")
	except Exception:
		return None


def _indexing() -> dict | None:
	"""Books in the catalogue against books the search engine lists, and what it still has to
	work through. The portal's search lists only what the engine has taken in, so while it is
	behind readers see fewer books than the catalogue holds."""
	cached = frappe.cache.get_value("resdesk:indexing")
	if cached is not None:
		return cached or None
	from sok_resdesk.search import MeiliClient

	try:
		client = MeiliClient.from_settings()
		listed = client.stats().get("indexes", {}).get(client.books, {}).get("numberOfDocuments", 0)
		tasks = client._req("GET", "/tasks", params={"statuses": "enqueued,processing", "limit": 1})
		waiting = tasks.get("total", 0)
	except Exception:
		frappe.cache.set_value("resdesk:indexing", {}, expires_in_sec=5)
		return None
	row = {
		"catalogue": frappe.db.count("RD Item", {"published": 1}),
		"listed": listed,
		"waiting": waiting,
		"unsent": frappe.db.count("RD Item", {"published": 1, "indexed_on": ("is", "not set")}),
	}
	frappe.cache.set_value("resdesk:indexing", row, expires_in_sec=5)
	return row


def machine() -> dict:
	from sok_resdesk import priority

	return {
		"priority": priority.status(),
		"indexing": _indexing(),
		"host": _host(),
		"limits": _limits(),
		"containers": _containers(),
		"search_size": _search_size(),
		"requested_preset": frappe.db.get_single_value("RD Settings", "resource_preset") or "",
		"native": not bool(_limits()),
	}


@frappe.whitelist()
def choose_preset(preset: str) -> dict:
	"""Record the resource preset chosen in the Desk; ./resdesk.sh resources apply uses it."""
	frappe.only_for(MANAGERS)
	if preset not in ("light", "standard", "server"):
		frappe.throw(_("Choose light, standard or server."))
	frappe.db.set_single_value("RD Settings", "resource_preset", preset)
	return {
		"message": _("Preset {0} chosen. On the server, run: ./resdesk.sh resources apply").format(preset)
	}


# -- quiet hours ---------------------------------------------------------------------------------


def quiet_status() -> dict:
	from frappe.utils import now_datetime as now

	from sok_resdesk.core.quiet import in_quiet_hours

	s = frappe.db.get_singles_dict("RD Settings")
	on = cint(s.get("quiet_hours"))
	inside = bool(
		on
		and in_quiet_hours(
			now(), s.get("quiet_from"), s.get("quiet_to"), bool(cint(s.get("quiet_weekdays_only")))
		)
	)
	return {
		"enabled": on,
		"inside": inside,
		"from": str(s.get("quiet_from") or "")[:5],
		"to": str(s.get("quiet_to") or "")[:5],
		"weekdays_only": cint(s.get("quiet_weekdays_only")),
	}


def apply_quiet_hours() -> None:
	"""Every few minutes (scheduler): Pause All when quiet hours start, Resume All when they end.

	Only the change of state acts, so a manager can still resume by hand during quiet hours
	(it stays resumed until the next quiet period), and a pause made by hand is never lifted."""
	q = quiet_status()
	state = frappe.db.get_default("resdesk_quiet_state") or "outside"
	who = "Quiet hours"
	if q["inside"] and state != "inside":
		if not holding.is_paused():
			_pause_all(who)
			frappe.db.set_default("resdesk_quiet_paused", "1")
		frappe.db.set_default("resdesk_quiet_state", "inside")
	elif not q["inside"] and state == "inside":
		if frappe.db.get_default("resdesk_quiet_paused") == "1" and holding.is_paused():
			_resume_all(who)
		frappe.db.set_default("resdesk_quiet_paused", "")
		frappe.db.set_default("resdesk_quiet_state", "outside")
	frappe.db.commit()
