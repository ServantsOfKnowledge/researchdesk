"""Classified mode (installer question, or `resdesk_classified` in the site configuration): an
installation for Secret and Top Secret records, to be run on its own air-gapped machine.

What it does, all of it outside the Desk's reach (the site configuration is not in the database):
  - refuses every outside web request that is not to a named internal host (a guard on `requests`);
  - keeps Governance Mode on, the portal behind sign-in, and the features that talk to outside
    services off, whatever the Settings form says;
  - keeps what readers searched for out of the audit log;
  - says on the Server page what it checks, and what only the deployment can (disk encryption,
    the network).
The guard covers the web requests Research Desk makes; the firewall around the machine is the
control that cannot be bypassed, and is yours to set up.
"""

from __future__ import annotations

import os
import smtplib
from urllib.parse import urlparse

import frappe
import requests
from frappe import _

from sok_resdesk.core import classified as rules

# features that talk to outside services: off here and not switchable on
OUTSIDE_FEATURES = ("sharing", "repositories", "authorities", "library_systems", "statistics")


class ClassifiedModeError(requests.exceptions.RequestException):
	"""An outside connection that classified mode refuses (callers that catch request errors cope)."""


def on() -> bool:
	return bool(frappe.conf.get("resdesk_classified") or os.environ.get("RESDESK_CLASSIFIED") == "1")


def allowed() -> list[str]:
	hosts = frappe.conf.get("resdesk_allowed_hosts") or []
	if isinstance(hosts, str):
		hosts = [hosts]
	urls = [
		frappe.conf.get("resdesk_meili_url"),
		frappe.db.get_single_value("RD Settings", "meili_url"),
		os.environ.get("RESDESK_DOCKER_API"),
	]
	return [*hosts, *(h for h in (urlparse(u or "").hostname for u in urls) if h)]


def _refuse(host) -> None:
	if on() and not rules.host_allowed(host, allowed()):  # per call: another site on this bench is not bound
		raise ClassifiedModeError(f"Classified mode: a connection to {host} is refused")


def install_guard(*_args, **_kwargs) -> None:
	"""before_request / before_job / before_migrate: wrap `requests` and outgoing mail so an outside
	address is refused. Idempotent."""
	if not on() or getattr(requests.sessions.Session.send, "_rd_guard", False):
		return
	send, connect = requests.sessions.Session.send, smtplib.SMTP.connect

	def guarded(self, request, **kw):
		_refuse(urlparse(request.url).hostname)
		return send(self, request, **kw)

	def guarded_connect(self, host="localhost", *args, **kw):
		_refuse(host)  # SMTP_SSL inherits connect
		return connect(self, host, *args, **kw)

	guarded._rd_guard, guarded._rd_orig = True, send
	guarded_connect._rd_orig = connect
	requests.sessions.Session.send = guarded
	smtplib.SMTP.connect = guarded_connect


def remove_guard() -> None:
	"""For tests."""
	send = requests.sessions.Session.send
	if getattr(send, "_rd_guard", False):
		requests.sessions.Session.send = send._rd_orig
		smtplib.SMTP.connect = smtplib.SMTP.connect._rd_orig


def enforce(doc) -> None:
	"""RD Settings is saved: what classified mode fixes stays fixed."""
	if not on():
		return
	doc.governance = 1
	doc.guest_access = "Login required"
	for key in OUTSIDE_FEATURES:
		if doc.meta.has_field(f"feature_{key}"):
			doc.set(f"feature_{key}", 0)
	for field, value in (("check_updates", 0), ("alert_webhook_url", "")):
		if doc.meta.has_field(field):
			doc.set(field, value)


def apply() -> None:
	"""after_migrate: bring an existing site into line."""
	if not on():
		return
	install_guard()
	doc = frappe.get_doc("RD Settings")
	enforce(doc)
	doc.save(ignore_permissions=True)
	# profiles that fetch from outside stop running by themselves (they would fail every time)
	frappe.db.sql(
		"update `tabRD Ingest Profile` set schedule = 'Manual' "
		"where source in ('Internet Archive', 'Repository (OAI-PMH)', 'Wikisource')"
	)
	frappe.db.commit()


def search_detail(mode: str, words: str) -> str:
	"""What the audit log keeps of a search: the words only when this is not a classified installation."""
	return mode if on() else f"{mode}: {words[:200]}"


def problems() -> list[str]:
	"""What the Server page should still warn about."""
	out = []
	if not requests.sessions.Session.send.__dict__.get("_rd_guard"):
		out.append(_("The outside-connection guard is not installed in this process."))
	if not frappe.db.get_single_value("RD Settings", "governance"):
		out.append(_("Governance Mode is off."))
	if frappe.db.get_single_value("RD Settings", "guest_access") != "Login required":
		out.append(_("The portal is not behind sign-in."))
	return out
