"""Joining the portal from its own page: what is accepted. Pure Python (no Frappe), so it is unit-tested.
sok_resdesk/signup.py applies it."""

from __future__ import annotations

import re

MIN_PASSWORD = 8
MAX_NAME = 140
MAX_EMAIL = 140
_TAGS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean(full_name, email, password, trap="") -> tuple[dict | None, str]:
	"""({"full_name", "email", "password"}, "") or (None, why). `why` is "trap" (a robot filled the hidden
	field: say nothing), "name", "email" or "password" (too short)."""
	if str(trap or "").strip():
		return None, "trap"
	name = " ".join(_CONTROL.sub("", _TAGS.sub("", str(full_name or ""))).split())[:MAX_NAME]
	if not name:
		return None, "name"
	address = str(email or "").strip().lower()
	if len(address) > MAX_EMAIL or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
		return None, "email"
	if len(str(password or "")) < MIN_PASSWORD:
		return None, "password"
	return {"full_name": name, "email": address, "password": str(password)}, ""


_NEXT = re.compile(r"/[A-Za-z0-9._~%/\-]*(\?[A-Za-z0-9._~%/=&\-]*)?")


def safe_next(url) -> str:
	"""Where to go after joining: only a plain path on this site. Browsers drop tabs and line breaks inside
	an address, so "/<tab>/evil.example" would become "//evil.example": anything but ordinary path
	characters is refused."""
	url = str(url or "")
	return url if _NEXT.fullmatch(url) and not url.startswith("//") else "/library"
