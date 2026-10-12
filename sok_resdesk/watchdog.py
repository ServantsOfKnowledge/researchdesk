"""Self-healing for the background jobs that carry on by themselves.

Sending page text to the search engine and scoring OCR quality each run as one job that queues
itself again. When the worker running one is restarted or killed, the job's record stays in Redis
and the job library then refuses to queue the same job again, so the work waits until a person
presses *Send now* or *Score now*. Every ten minutes this looks at those jobs: when there is work
waiting and the job's record is not backed by a queue or a worker, it clears the record and queues
the job again, and writes down what it did (Background Jobs → Machine shows the last repair).

It only repairs a record it has seen dead on two checks in a row, never while background work is
paused or stopped, and never starts work nobody asked for: it does not queue a job that has no
record. Deleting a dead record and queueing the same job again loses nothing: both jobs read
their work from the database."""

import frappe
from frappe.utils import cint, now_datetime

from sok_resdesk.core import watchdog as core

LOG_KEY = "resdesk:watchdog-log"


def job_state(job_id: str) -> str:
	""" "none", "alive" or "dead" for the job on record under this id (see core.watchdog.judge)."""
	from frappe.utils.background_jobs import create_job_id, get_redis_conn
	from rq import Queue, Worker
	from rq.exceptions import NoSuchJobError
	from rq.job import Job

	full = create_job_id(job_id)
	conn = get_redis_conn()
	try:
		job = Job.fetch(full, connection=conn)
	except NoSuchJobError:
		return "none"
	except Exception:
		return "dead"  # a half-written record (KeyError: b'created_at')
	status = job.get_status(refresh=True)
	status = str(getattr(status, "value", status))
	in_queue = status == "queued" and full in Queue(job.origin, connection=conn).job_ids
	running = status == "started" and any(w.get_current_job_id() == full for w in Worker.all(connection=conn))
	return core.judge(status, in_queue, running)


def _sender_waiting() -> bool:
	if cint(frappe.db.get_single_value("RD Settings", "hold_page_text")):
		return False  # held on purpose
	return bool(frappe.db.count("RD Item", {"pages_pending": 1}))


def _score_waiting() -> bool:
	from sok_resdesk import ocr

	return bool(ocr.unscored(1))


def _chains() -> list[tuple[str, str, object, object]]:
	"""(job id, what it does, is work waiting, queue it again)."""
	from sok_resdesk import ocr, search_queue

	return [
		(search_queue.SENDER_JOB, "sending page text", _sender_waiting, search_queue._queue_send),
		(ocr.SCORE_JOB, "scoring OCR quality", _score_waiting, ocr.queue_scoring),
	]


def is_quiet() -> bool:
	"""Background work is paused or was stopped a moment ago: nothing to repair now."""
	from sok_resdesk.holding import is_paused

	return bool(is_paused() or frappe.cache.get_value("resdesk:stop-background"))


def run() -> list[str]:
	"""Scheduler, every ten minutes. Returns what it repaired."""
	if is_quiet():
		return []
	repaired = []
	for job_id, what, waiting, queue_again in _chains():
		seen_key = f"resdesk:watchdog-seen:{job_id}"
		try:
			if not waiting() or job_state(job_id) != "dead":
				frappe.cache.delete_value(seen_key)
				continue
			if not frappe.cache.get_value(seen_key):
				frappe.cache.set_value(seen_key, 1, expires_in_sec=core.CONFIRM_MINUTES * 60)
				continue  # seen once: the next check decides
			from sok_resdesk.search_queue import forget_job

			forget_job(job_id)
			queue_again()
			frappe.cache.delete_value(seen_key)
			note = f"{what}: a job whose worker had stopped was cleared and queued again"
			_write(note)
			repaired.append(note)
		except Exception:
			frappe.log_error(title=f"Research Desk watchdog: could not check {what}")
	return repaired


def _write(what: str) -> None:
	log = core.remember(frappe.cache.get_value(LOG_KEY), str(now_datetime())[:19], what)
	frappe.cache.set_value(LOG_KEY, log, expires_in_sec=30 * 24 * 3600)
	frappe.logger("resdesk").info("watchdog: %s", what)


def last_repairs(n: int = 3) -> list[dict]:
	"""The latest repairs, newest first, for Background Jobs → Machine."""
	return list(frappe.cache.get_value(LOG_KEY) or [])[:n]
