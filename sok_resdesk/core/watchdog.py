"""The self-healing watchdog's judgement (pure: no Redis, no database)."""

from datetime import datetime, timedelta

QUEUED = ("queued", "scheduled", "deferred")
KEEP = 20  # repairs kept in the log
CONFIRM_MINUTES = 30  # a sighting counts as "again" if it was made within this long ago
MAIL_MAX_AGE_HOURS = (
	12  # a failed email is sent again only while its sign-in link is fresh (link life is 24 h)
)
MAIL_IDLE_MINUTES = 30  # ...and only after it has been left alone this long, so a mail outage is not hammered
MAIL_BATCH = 20  # failed emails put back per run


def judge(status: str | None, in_queue: bool, running: bool) -> str:
	"""Is a background job on record alive? Returns "none" (no record), "alive" or "dead".

	A job that is queued must be in a queue, and a job that is started must be on a worker. A
	record that claims either while neither is true belongs to a worker that was restarted or
	killed, and the job library then refuses to queue the same job again. Finished, failed and
	cancelled records make no such claim."""
	if status is None:
		return "none"
	if status == "started":
		return "alive" if running else "dead"
	if status in QUEUED:
		return "alive" if in_queue or status != "queued" else "dead"
	return "alive"


def remember(log: list[dict] | None, at: str, what: str) -> list[dict]:
	"""The repair log with one more entry, newest first, no longer than KEEP."""
	return ([{"at": at, "what": what}] + list(log or []))[:KEEP]


def mail_window(now: datetime) -> tuple[datetime, datetime]:
	"""(created after, last changed before): the failed emails worth sending again are in between."""
	return now - timedelta(hours=MAIL_MAX_AGE_HOURS), now - timedelta(minutes=MAIL_IDLE_MINUTES)
