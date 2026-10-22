"""Messages from people who visit the portal: what is accepted, and what is said to the Desk's alert.

Pure Python (no Frappe), so it is unit-tested. sok_resdesk/contact.py applies it.
"""

from __future__ import annotations

import re

MAX_NAME = 140
MAX_CONTACT = 140
MIN_MESSAGE = 10
MAX_MESSAGE = 2000
FLOOD_PER_HOUR = 60  # all visitors together: past this the form asks people to come back later

_TAGS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _plain(text, limit: int, keep_lines: bool = False) -> str:
	text = _CONTROL.sub("", _TAGS.sub("", str(text or "")))
	if not keep_lines:
		text = " ".join(text.split())
	else:
		text = "\n".join(" ".join(line.split()) for line in text.replace("\r", "").split("\n")).strip()
		text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()[:limit]


def clean(name, contact, message, trap="") -> tuple[dict | None, str]:
	"""(the fields to keep, "") or (None, why): why is "trap" (a robot filled the hidden field: say
	nothing), "short" or "empty" (no message of any use)."""
	if str(trap or "").strip():
		return None, "trap"
	body = _plain(message, MAX_MESSAGE, keep_lines=True)
	if not body:
		return None, "empty"
	if len(body) < MIN_MESSAGE:
		return None, "short"
	return {
		"full_name": _plain(name, MAX_NAME),
		"contact": _plain(contact, MAX_CONTACT),
		"message": body,
	}, ""


def too_many(count_last_hour: int, cap: int = FLOOD_PER_HOUR) -> bool:
	return count_last_hour >= cap


def alert_text(portal: str, url: str) -> str:
	"""What Telegram is told: that a message came and where to read it, never the message itself."""
	return f"{portal}: a visitor sent a message. Read it in the Desk: {url}"
