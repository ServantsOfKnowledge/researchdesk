"""Directory sign-in rules: what an LDAP or single sign-on setup may be, and when a leaver is cut off.
Pure Python, no Frappe.

A directory proves who someone is. It must not decide what duties they hold: the duties that carry
the governance (security officer, records officer, super admin, system manager) are given in the
Desk by people, so a compromised or careless directory cannot promote anyone to them.
"""

from __future__ import annotations

from urllib.parse import urlparse

PRIVILEGED = (
	"Administrator",
	"System Manager",
	"SOK Super Admin",
	"ResDesk Security Officer",
	"ResDesk Records Officer",
	"Script Manager",
	"Server Script Manager",
	"Workspace Manager",
	"Website Manager",
)
BRAKE_SHARE = 5  # a run that would switch off more than 1 in this many tracked people stops instead
GRACE_RUNS = 2  # consecutive daily checks that must miss a person before they are switched off
LOCAL = ("localhost", "127.0.0.1", "::1")


def privileged_mapped(roles, allowed=()) -> list[str]:
	"""The roles among `roles` that a directory may not hand out (unless the site configuration allows)."""
	# a role is matched however it is spelt: the database ignores case, and Frappe corrects it only later
	held = {p.casefold(): p for p in PRIVILEGED}
	ok = {a.strip().casefold() for a in allowed}
	return sorted(
		{
			held[r.strip().casefold()]
			for r in roles
			if (r or "").strip().casefold() in held and r.strip().casefold() not in ok
		}
	)


def ldap_connection_problems(url: str, tls_mode: str, trusted: str) -> list[str]:
	"""Why an LDAP connection would send passwords where they can be read or be sent to an impostor."""
	out = []
	if not (url or "").lower().startswith("ldaps://") and tls_mode != "StartTLS":
		out.append("use ldaps:// or StartTLS: passwords must not cross the network in the clear")
	if trusted != "Yes":
		out.append("require a trusted certificate, so the server is the one it claims to be")
	return out


def https_or_local(url: str) -> bool:
	u = urlparse((url or "").strip())
	return u.scheme == "https" or (u.scheme == "http" and (u.hostname or "").lower() in LOCAL)


def missing_after(missing: int, found: bool) -> int:
	"""The running count of consecutive checks that did not find the person."""
	return 0 if found else missing + 1


def to_switch_off(missing: int) -> bool:
	return missing >= GRACE_RUNS


def too_many(leaving: int, tracked: int) -> bool:
	"""More than 1 in BRAKE_SHARE (and more than two people): the check is more likely wrong than the
	directory, so nobody is switched off this time."""
	return leaving > max(2, tracked // BRAKE_SHARE)
