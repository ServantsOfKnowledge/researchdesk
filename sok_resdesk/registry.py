"""The install note. A site may tell Servants of Knowledge that it exists: a random ID, the version, the edition,
how it was installed and the kinds of institution. Once after install and then about once a month, never from
a Classified site or the governance edition, and only when the Settings box is ticked.

The same code receives the notes on research.servantsofknowledge.in (Settings → *This site is the registry*,
off everywhere else): one record per ID, no IP address, no other detail (docs/install-count.md).
"""

from __future__ import annotations

import json
import os
import sys
import uuid

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate

from sok_resdesk import features, seams
from sok_resdesk.core import registry as rules

MANAGERS = ("System Manager", "SOK Super Admin", "ResDesk Manager")
MAX_NEW_PER_DAY = 500  # a registry that is being filled with made-up ids stops taking new ones
MAX_BYTES = 2048


def _blocked() -> str:
	"""Why this site must not send a note (empty: it may)."""
	if seams.classified():
		return _("This is a Classified installation: it makes no outside connections.")
	if "sok_resdesk_governance" in frappe.get_installed_apps():
		return _("The governance edition never sends one.")
	if not cint(frappe.db.get_single_value("RD Settings", "share_install_info")):
		return _("Switched off in Settings.")
	return ""


def _kind() -> str:
	if os.path.exists("/.dockerenv"):
		return "docker"
	return {"darwin": "macos", "linux": "linux"}.get(sys.platform, "other")


def instance_id() -> str:
	"""The random ID of this install, made the first time it is needed and never changed."""
	value = frappe.db.get_single_value("RD Settings", "instance_id")
	if not value:
		value = str(uuid.uuid4())
		frappe.db.set_single_value("RD Settings", "instance_id", value)
	return value


def current_note() -> dict:
	from sok_resdesk import __version__

	s = frappe.get_single("RD Settings")
	return rules.payload(
		instance_id(),
		__version__,
		"governance" if "sok_resdesk_governance" in frappe.get_installed_apps() else "standard",
		_kind(),
		[k for k in features.PROFILES if s.get(f"profile_{k}")],
	)


@frappe.whitelist(methods=["POST"])  # it may make the install ID, which a GET would not keep
def preview() -> dict:
	"""What would be sent, where to, whether it may be, and when the last one went (managers)."""
	frappe.only_for(MANAGERS)
	why = _blocked()
	return {
		"note": current_note(),
		"to": rules.ENDPOINT,
		"blocked": why,
		"last_sent": str(frappe.db.get_single_value("RD Settings", "registry_last_sent") or ""),
	}


def send() -> dict:
	"""Send the note now, if the site may."""
	import requests

	why = _blocked()
	if why:
		return {"sent": 0, "why": why}
	note = current_note()
	try:
		reply = requests.post(rules.ENDPOINT, json=note, timeout=10, allow_redirects=False)
		ok = reply.status_code == 200
	except requests.RequestException:
		ok = False
	if ok:
		frappe.db.set_single_value("RD Settings", "registry_last_sent", now_datetime())
		frappe.db.set_single_value("RD Settings", "registry_last_note", json.dumps(note, indent=1))
	return {"sent": int(ok), "why": "" if ok else _("Could not reach research.servantsofknowledge.in.")}


@frappe.whitelist(methods=["POST"])
def send_now() -> dict:
	frappe.only_for(MANAGERS)
	return send()


def daily() -> None:
	"""About once a month (and the first time after it is switched on); a failure is simply tried again tomorrow."""
	if _blocked():
		return
	if rules.due(frappe.db.get_single_value("RD Settings", "registry_last_sent"), getdate(nowdate())):
		send()
		frappe.db.commit()


# -- the receiving end (research.servantsofknowledge.in only) ---------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def ping() -> dict:
	"""Take one install note. Does nothing, and says so as if the page did not exist, unless this site is the
	registry. Keeps the ID, the version, the edition, the kind, the profiles and two dates: no address."""
	if not cint(frappe.db.get_single_value("RD Settings", "registry_receive")):
		raise frappe.DoesNotExistError
	req = frappe.request
	if (
		not (req and (req.content_type or "").startswith("application/json"))
		or (req.content_length or 0) > MAX_BYTES
	):
		frappe.throw(_("Not a note."), frappe.ValidationError)
	note = rules.valid(req.get_json(silent=True))
	if not note:
		frappe.throw(_("Not a note."), frappe.ValidationError)
	if not take(note):
		frappe.throw(_("Too many new installations today. Try again tomorrow."), frappe.ValidationError)
	return {"ok": 1}


def take(note: dict) -> bool:
	"""Keep one cleaned note: a new record, or the existing one brought up to date. False when today's limit of
	new installations is reached (the sender then sees an error and tries again tomorrow, not a false success)."""
	now = now_datetime()
	existing = frappe.db.get_value("RD Install Ping", note["id"], ["name", "last_seen"], as_dict=True)
	if existing:
		if existing.last_seen and (now - existing.last_seen).total_seconds() < 3600:
			return True  # an hour is enough between notes from one install
		frappe.db.set_value(
			"RD Install Ping",
			note["id"],
			{
				"version": note["version"],
				"edition": note["edition"],
				"kind": note["kind"],
				"profiles": ",".join(note["profiles"]),
				"last_seen": now,
				"pings": cint(frappe.db.get_value("RD Install Ping", note["id"], "pings")) + 1,
			},
		)
		return True
	if frappe.db.count("RD Install Ping", {"first_seen": (">=", add_days(nowdate(), 0))}) >= MAX_NEW_PER_DAY:
		return False
	try:
		frappe.get_doc(
			{
				"doctype": "RD Install Ping",
				"instance_id": note["id"],
				"version": note["version"],
				"edition": note["edition"],
				"kind": note["kind"],
				"profiles": ",".join(note["profiles"]),
				"first_seen": now,
				"last_seen": now,
				"pings": 1,
			}
		).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:  # the same install's first two notes arrived together
		pass
	return True


@frappe.whitelist()
def summary() -> dict:
	"""How many installs have been heard from and are still sending (System Manager, on the registry only)."""
	frappe.only_for(("System Manager", "SOK Super Admin"))
	rows = frappe.get_all(
		"RD Install Ping", fields=["last_seen", "version", "edition", "kind", "profiles"], limit_page_length=0
	)
	for r in rows:
		r["last_seen"] = getdate(r["last_seen"])
	return rules.summarize(rows, getdate(nowdate()))
