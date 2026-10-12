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
	repaired += sweep()
	repaired += retry_mail()
	return repaired


def retry_mail() -> list[str]:
	"""Failed sign-in and sign-up emails, recent and left alone for a while, go back in the queue so they
	leave once the mail account works again. Older ones stay failed: their link has aged, and Server →
	Send a new link is better than an old one. Frappe's own three tries happen inside each attempt."""
	created_after, idle_before = core.mail_window(now_datetime())
	try:
		names = frappe.db.sql_list(
			"select name from `tabEmail Queue` where status = 'Error' and creation > %s and modified < %s"
			" limit %s",
			(created_after, idle_before, core.MAIL_BATCH),
		)
		if not names:
			return []
		frappe.db.sql(
			"update `tabEmail Queue` set status = 'Not Sent', error = null where name in %s", (names,)
		)
		note = f"Email: {len(names)} failed email(s) put back in the queue to be sent again"
		_write(note)
		return [note]
	except Exception:
		frappe.log_error(title="Research Desk watchdog: could not retry failed emails")
		return []


def _record_ids() -> list[str]:
	"""The ids of every Research Desk job on record in Redis for this site (without the site prefix)."""
	from frappe.utils.background_jobs import create_job_id, get_redis_conn

	prefix = create_job_id("resdesk-")  # "<site>::resdesk-"
	found = []
	for raw in get_redis_conn().scan_iter(match=f"rq:job:{prefix}*", count=1000):
		key = raw.decode() if isinstance(raw, bytes) else raw
		found.append(key.removeprefix("rq:job:").split("::", 1)[1])
	return found


def sweep() -> list[str]:
	"""Any other Research Desk job (a fixity audit, a review scan, one book's re-OCR…) whose record is
	held by no queue and no worker on two checks in a row has its record cleared. It is not queued again:
	nothing says work is waiting, and the job's own schedule or button starts it next time. Without
	this the dead record made every later start of the same job quietly do nothing."""
	from sok_resdesk.search_queue import forget_job

	done = []
	try:
		ids = _record_ids()
	except Exception:
		return done  # no Redis to look at
	for job_id in ids:
		seen_key = f"resdesk:watchdog-seen:{job_id}"
		try:
			if job_state(job_id) != "dead":
				frappe.cache.delete_value(seen_key)
				continue
			if not frappe.cache.get_value(seen_key):
				frappe.cache.set_value(seen_key, 1, expires_in_sec=core.CONFIRM_MINUTES * 60)
				continue
			forget_job(job_id)
			frappe.cache.delete_value(seen_key)
			note = f"{job_id}: a job whose worker had stopped was cleared"
			_write(note)
			done.append(note)
		except Exception:
			frappe.log_error(title=f"Research Desk watchdog: could not check {job_id}")
	return done


def _write(what: str) -> None:
	log = core.remember(frappe.cache.get_value(LOG_KEY), str(now_datetime())[:19], what)
	frappe.cache.set_value(LOG_KEY, log, expires_in_sec=30 * 24 * 3600)
	frappe.logger("resdesk").info("watchdog: %s", what)


def last_repairs(n: int = 3) -> list[dict]:
	"""The latest repairs, newest first, for Background Jobs → Machine."""
	return list(frappe.cache.get_value(LOG_KEY) or [])[:n]
