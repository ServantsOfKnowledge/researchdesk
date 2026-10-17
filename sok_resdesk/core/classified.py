"""Classified mode: which outside addresses a classified installation may still reach. Pure Python.

Everything outside the allowlist is refused. The allowlist is the machine itself and the hosts the
administrator names (the search engine's own address, an internal mirror, a directory server).
"""

from __future__ import annotations

LOCAL = ("localhost", "127.0.0.1", "::1")


def host_allowed(host: str | None, allowed) -> bool:
	"""`allowed`: exact names, or a leading dot for a whole domain (".gov.example" = it and its subdomains)."""
	host = (host or "").strip().lower().rstrip(".")
	if not host:
		return False
	for rule in (*LOCAL, *(a.strip().lower().rstrip(".") for a in allowed or [] if a and a.strip())):
		if rule.startswith("."):
			if host == rule[1:] or host.endswith(rule):
				return True
		elif host == rule:
			return True
	return False
