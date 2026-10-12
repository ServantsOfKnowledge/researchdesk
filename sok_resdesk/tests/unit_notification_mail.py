"""Frappe's own notifications are kept out of email (hooks.py)."""

import ast
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks.py"


def test_frappe_notification_types_do_not_email():
	value = next(
		ast.literal_eval(n.value)
		for n in ast.parse(HOOKS.read_text(encoding="utf-8")).body
		if isinstance(n, ast.Assign) and n.targets[0].id == "notification_skip_email_types"
	)
	assert {"Mention", "Assignment", "Share", "Energy Point"} <= set(value)
