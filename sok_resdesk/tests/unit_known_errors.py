"""0.68.7: matching Error Log entries to the release that fixed them."""

from sok_resdesk.core import known_errors as k

HIST = [("0.68.2", "2026-11-07 09:00:00"), ("0.68.6", "2026-11-07 16:00:00")]


def test_entries_are_matched_by_their_text():
	assert k.match("KeyError: b'created_at'").key == "rq-created-at"
	assert k.match("Record has changed since last read").key == "record-changed"
	assert k.match("pymysql.err.OperationalError: (1020, 'Record has changed')").key == "record-changed"
	assert k.match("something nobody has seen") is None


def test_versions_compare_as_numbers():
	assert k.at_least("0.68.10", "0.68.6") and not k.at_least("0.68.5", "0.68.6")
	assert k.at_least("0.69.0", "0.68.6")


def test_verdicts():
	rq = k.match("b'created_at'")
	# the fix (0.68.6) is installed since 16:00: older entries are resolved, newer ones recur
	assert k.verdict(rq, "0.68.6", "2026-11-07 12:00:00", HIST) == "resolved"
	assert k.verdict(rq, "0.68.6", "2026-11-07 17:00:00", HIST) == "recurring"
	# not installed yet
	assert k.verdict(rq, "0.68.2", "2026-11-07 12:00:00", HIST[:1]) == "upgrade"
	# installed but no record of when
	assert k.verdict(rq, "0.68.6", "2026-11-07 12:00:00", []) == "unsure"


def test_every_known_error_names_a_release_and_a_pattern():
	import re

	keys = [x.key for x in k.KNOWN]
	assert len(keys) == len(set(keys))
	for x in k.KNOWN:
		re.compile(x.pattern)
		assert k.version_tuple(x.fixed_in) != (0, 0, 0)
		assert x.title and x.note


def test_a_repair_note_is_information_never_a_fault():
	note = k.match("the page-text sender's old record was damaged; cleared")
	assert k.verdict(note, "0.68.6", "2026-11-08 10:00:00", HIST) == "info"
