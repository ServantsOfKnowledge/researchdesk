"""Who may find and read what. Pure Python, no Frappe: unit-tested in tests/test_core.py.

Each book has a visibility:
  Public         anyone can find it, read it and search inside it
  Login to read  anyone can find it and cite it; reading, search inside and the PDF need a login
  Login to find  only logged-in readers know it exists

The site decides how guests (visitors who are not logged in) are treated:
  Each item's setting   guests follow each book's visibility (the default)
  Records only          guests can find and cite, but never read: a catalogue for the public
  Login required        guests see nothing but the login page: an internal library

Readers (logged-in members) and staff can find and read everything that is published.
"""

from __future__ import annotations

PUBLIC = "Public"
LOGIN_TO_READ = "Login to read"
LOGIN_TO_FIND = "Login to find"
VISIBILITIES = (PUBLIC, LOGIN_TO_READ, LOGIN_TO_FIND)

GUEST_ITEM = "Each item's setting"
GUEST_RECORDS = "Records only"
GUEST_NONE = "Login required"
GUEST_MODES = (GUEST_ITEM, GUEST_RECORDS, GUEST_NONE)

SIGNUP_CLOSED = "Admins add readers"
SIGNUP_OPEN = "Anyone can sign up"
SIGNUP_APPROVE = "Sign up, admin approves"
SIGNUP_MODES = (SIGNUP_CLOSED, SIGNUP_OPEN, SIGNUP_APPROVE)

RULE_FIELDS = ("Collection", "Subject", "Language", "Creator", "Source", "Ingest Profile")


def normalise(visibility: str | None) -> str:
	"""Unknown or empty values count as Public (records indexed before access control existed)."""
	return visibility if visibility in VISIBILITIES else PUBLIC


def can_find(visibility: str | None, guest_mode: str | None, member: bool) -> bool:
	if member:
		return True
	if guest_mode == GUEST_NONE:
		return False
	return normalise(visibility) != LOGIN_TO_FIND


def can_read(visibility: str | None, guest_mode: str | None, member: bool) -> bool:
	if member:
		return True
	if guest_mode in (GUEST_NONE, GUEST_RECORDS):
		return False
	return normalise(visibility) == PUBLIC


def search_filter(kind: str, guest_mode: str | None, member: bool) -> str | None:
	"""Meilisearch filter limiting a guest's results.

	Returns None for "no restriction" and "" for "nothing at all". Uses NOT so that documents
	indexed before the visibility field existed still count as Public (Meilisearch's != and
	NOT IN skip documents that lack the field; NOT includes them).
	"""
	if member:
		return None
	if guest_mode == GUEST_NONE:
		return ""
	if kind == "pages":
		if guest_mode == GUEST_RECORDS:
			return ""
		return f'NOT visibility IN ["{LOGIN_TO_READ}", "{LOGIN_TO_FIND}"]'
	return f'NOT visibility = "{LOGIN_TO_FIND}"'


def sql_condition(guest_mode: str | None, member: bool, column: str = "visibility") -> str:
	"""SQL WHERE fragment for records a viewer can find (published is checked separately)."""
	if member:
		return "1=1"
	if guest_mode == GUEST_NONE:
		return "1=0"
	return f"ifnull({column}, '') != '{LOGIN_TO_FIND}'"


def _values(record: dict, field: str) -> list[str]:
	if field == "Collection":
		values = record.get("collections") or []
	elif field == "Subject":
		values = record.get("subjects") or []
	elif field == "Creator":
		values = record.get("creators") or []
	elif field == "Language":
		values = [record.get("language_label") or "", record.get("language") or ""]
	elif field == "Source":
		values = [record.get("source") or ""]
	elif field == "Ingest Profile":
		values = [record.get("ingest_profile") or ""]
	else:
		values = []
	return [str(v).strip().casefold() for v in values if v]


def match_rule(record: dict, rules: list[dict]) -> dict | None:
	"""First rule (in table order) whose field has the given value; case-insensitive."""
	for rule in rules or []:
		field, value = rule.get("match_on"), (rule.get("value") or "").strip().casefold()
		if value and rule.get("visibility") in VISIBILITIES and value in _values(record, field):
			return rule
	return None


def initial_visibility(record: dict, profile_visibility: str | None, rules: list[dict],
					   default: str | None) -> tuple[str, str]:
	"""Visibility for a newly ingested book, and what set it.

	The ingest profile's own setting wins, then the first matching rule, then the site default.
	"""
	if profile_visibility in VISIBILITIES:
		return profile_visibility, "Profile"
	rule = match_rule(record, rules)
	if rule:
		return rule["visibility"], f"Rule: {rule['match_on']} = {rule['value']}"[:140]
	return normalise(default), "Default"
