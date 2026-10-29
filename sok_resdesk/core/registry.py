"""The install note: what a Research Desk tells Servants of Knowledge that it exists, and the count made from
the notes. Pure Python; nothing here reads a site or the network.

The note is a random ID made on the machine, the version, the edition, how it was installed and the kinds of
institution chosen. It has no name, address, domain or user, and never leaves a site that is Classified or
runs the governance edition (docs/install-count.md).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta

ENDPOINT = "https://research.servantsofknowledge.in/api/method/sok_resdesk.registry.ping"
SEND_EVERY_DAYS = 28
ACTIVE_DAYS = 45  # an install that has not sent a note for this long is no longer counted as running
EDITIONS = ("standard", "governance")
KINDS = ("docker", "macos", "linux", "other")
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_VERSION = re.compile(r"^\d{1,3}\.\d{1,4}\.\d{1,4}$")
_PROFILE = re.compile(r"^[a-z_]{1,24}$")
MAX_PROFILES = 12


def payload(instance_id: str, version: str, edition: str, kind: str, profiles) -> dict:
	"""The whole note. Exactly these five things, and nothing else."""
	return {
		"id": instance_id,
		"version": version,
		"edition": edition,
		"kind": kind,
		"profiles": sorted({p for p in profiles or [] if _PROFILE.match(p)})[:MAX_PROFILES],
	}


def valid(data) -> dict | None:
	"""A received note, cleaned, or None when it is not exactly a note (wrong keys, shapes or sizes)."""
	if not isinstance(data, dict) or set(data) != {"id", "version", "edition", "kind", "profiles"}:
		return None
	profiles = data["profiles"]
	if (
		not (isinstance(data["id"], str) and _ID.match(data["id"]))
		or not (isinstance(data["version"], str) and _VERSION.match(data["version"]))
		or data["edition"] not in EDITIONS
		or data["kind"] not in KINDS
		or not isinstance(profiles, list)
		or len(profiles) > MAX_PROFILES
		or not all(isinstance(p, str) and _PROFILE.match(p) for p in profiles)
	):
		return None
	return payload(data["id"], data["version"], data["edition"], data["kind"], profiles)


def due(last_sent: date | datetime | None, today: date) -> bool:
	"""Never sent, or the last note is SEND_EVERY_DAYS old."""
	if not last_sent:
		return True
	d = last_sent.date() if isinstance(last_sent, datetime) else last_sent
	return today - d >= timedelta(days=SEND_EVERY_DAYS)


def summarize(rows: list[dict], today: date) -> dict:
	"""Counts from the received notes: `rows` have last_seen (date), version, edition, kind, profiles (comma text)."""
	active = [r for r in rows if (today - r["last_seen"]).days <= ACTIVE_DAYS]
	profiles = Counter(p for r in active for p in (r.get("profiles") or "").split(",") if p)
	return {
		"ever": len(rows),
		"active": len(active),
		"versions": dict(Counter(r["version"] for r in active)),
		"editions": dict(Counter(r["edition"] for r in active)),
		"kinds": dict(Counter(r["kind"] for r in active)),
		"profiles": dict(profiles),
	}
