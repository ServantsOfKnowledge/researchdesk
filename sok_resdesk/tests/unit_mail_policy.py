"""Email is for account messages only: no new place may send mail without being listed here."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
# the test message an administrator asks for, a fresh password link a manager asks for, and the
# answer to someone who asked for a reader account
ALLOWED = {"mail.py", "clock.py", "rd_reader_request.py"}
SENDERS = re.compile(r"frappe\.sendmail\(|sendmail\(|send_email=True|\.send_mail\(")


def test_only_account_mail_is_sent():
	found = set()
	for path in APP.rglob("*.py"):
		if "tests" in path.parts or "patches" in path.parts:
			continue
		if SENDERS.search(path.read_text(encoding="utf-8")):
			found.add(path.name)
	assert found <= ALLOWED, (
		f"These send email; email is for account messages only: {sorted(found - ALLOWED)}"
	)
