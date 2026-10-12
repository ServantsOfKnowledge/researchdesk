"""The self-healing watchdog's judgement (pure: no Redis, no database)."""

QUEUED = ("queued", "scheduled", "deferred")
KEEP = 20  # repairs kept in the log
CONFIRM_MINUTES = 30  # a sighting counts as "again" if it was made within this long ago


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
