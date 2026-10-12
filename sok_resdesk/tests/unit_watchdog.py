"""The watchdog's judgement of a job on record (core/watchdog.py)."""

from sok_resdesk.core.watchdog import KEEP, judge, remember


def test_no_record_is_not_a_ghost():
	assert judge(None, False, False) == "none"


def test_queued_job_must_be_in_a_queue():
	assert judge("queued", True, False) == "alive"
	assert judge("queued", False, False) == "dead"


def test_started_job_must_be_on_a_worker():
	assert judge("started", False, True) == "alive"
	assert judge("started", False, False) == "dead"


def test_finished_and_failed_records_make_no_claim():
	for status in ("finished", "failed", "canceled", "stopped"):
		assert judge(status, False, False) == "alive"


def test_repair_log_is_newest_first_and_bounded():
	log = None
	for n in range(KEEP + 5):
		log = remember(log, f"t{n}", f"w{n}")
	assert len(log) == KEEP
	assert log[0] == {"at": f"t{KEEP + 4}", "what": f"w{KEEP + 4}"}
