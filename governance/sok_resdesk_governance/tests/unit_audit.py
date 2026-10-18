"""The audit log's hash chain (core/audit.py): tampering and removal show."""

from sok_resdesk_governance.core.audit import FIRST, row_hash, verify


def chain(n=4):
	rows, prev = [], FIRST
	for i in range(1, n + 1):
		row = {
			"seq": i,
			"event_time": f"2026-10-17 10:0{i}:00",
			"user": "a@x.org",
			"event": "view",
			"item": f"b{i}",
		}
		row |= {"prev_hash": prev, "row_hash": row_hash(prev, row)}
		rows.append(row)
		prev = row["row_hash"]
	return rows


def test_an_untouched_log_is_intact():
	ok = verify(chain())
	assert ok["ok"] and ok["checked"] == 4 and ok["last"] == 4
	assert verify([])["checked"] == 0


def test_a_changed_line_is_found():
	rows = chain()
	rows[1]["user"] = "someone-else"
	assert verify(rows)["at"] == 2


def test_a_removed_line_is_found():
	rows = chain()
	del rows[2]
	assert verify(rows)["at"] == 3 and verify(rows)["why"] == "a line is missing"


def test_a_rewritten_line_that_keeps_its_own_hash_still_breaks_the_next():
	rows = chain()
	rows[1]["detail"] = "x"
	rows[1]["row_hash"] = row_hash(rows[1]["prev_hash"], rows[1])
	assert verify(rows)["at"] == 3


def test_the_chain_cannot_be_recomputed_without_the_key():
	rows, prev = [], FIRST
	for i in (1, 2):
		row = {"seq": i, "event": "view", "item": f"b{i}", "prev_hash": prev}
		row["row_hash"] = row_hash(prev, row, b"secret")
		rows.append(row)
		prev = row["row_hash"]
	assert verify(rows, b"secret")["ok"]
	assert not verify(rows, b"")["ok"]
