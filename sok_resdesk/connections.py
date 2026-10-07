"""Desk → Connections: every outside system Research Desk works with, by kind, in one place.

For each connection: what it does, whether it is switched on or connected (for me), who may use
it, and where to open it. The catalogue is core/connections.py; this adds the live status.
"""

from __future__ import annotations

import frappe
from frappe import _

from sok_resdesk import features
from sok_resdesk.core import connections as core

WHO_MAY_OPEN = core.WORKERS


def _count(doctype: str, filters=None) -> int:
	try:
		return frappe.db.count(doctype, filters or {})
	except Exception:
		return 0


def _mine(doctype: str) -> str:
	"""The connected account's name for the signed-in person, or ''."""
	field = {"RD Archive Account": "ia_user", "RD Wikimedia Account": "wikimedia_user"}[doctype]
	try:
		return frappe.db.get_value(doctype, frappe.session.user, field) or ""
	except Exception:
		return ""


def _targets(kind: str) -> int:
	return _count("RD Push Target", {"target_type": kind, "enabled": 1})


def _status(c: core.Card) -> dict:
	"""{state: ok | todo | off | info, text}: where this connection stands, for this person."""
	if c.feature and not features.on(c.feature):
		return {"state": "off", "text": _("Switched off in Settings → Features")}
	key = c.key
	if key == "ia_send":
		who = _mine("RD Archive Account")
		return (
			{"state": "ok", "text": _("Connected as {0}").format(who)}
			if who
			else {"state": "todo", "text": _("Not connected: connect your archive.org account")}
		)
	if key == "wm_account":
		who = _mine("RD Wikimedia Account")
		return (
			{"state": "ok", "text": _("Connected as {0}").format(who)}
			if who
			else {"state": "todo", "text": _("Not connected: connect your Wikimedia account")}
		)
	if key == "mail":
		from sok_resdesk import mail

		if not mail.ready():
			return {"state": "todo", "text": _("Not set up: sign-in and sign-up emails are not sent")}
		left = mail.stuck()
		if left["failed"]:
			return {"state": "todo", "text": _("{0} emails failed to send").format(left["failed"])}
		return {"state": "ok", "text": _("Set up")}
	if key == "ia_bring":
		n = _count("RD Ingest Profile", {"source": "Internet Archive"})
		return {"state": "ok" if n else "info", "text": _("Profiles: {0}").format(n)}
	if key == "ia_metadata":
		n = _targets("Internet Archive")
		return {"state": "ok" if n else "info", "text": _("Push targets on: {0}").format(n)}
	if key == "koha":
		n = _count("RD Library System")
		return {"state": "ok" if n else "info", "text": _("Library systems: {0}").format(n)}
	if key == "webhooks":
		n = _targets("Webhook")
		return {"state": "ok" if n else "info", "text": _("Webhooks on: {0}").format(n)}
	if key == "deposit":
		n = _count("RD Deposit", {"status": "Submitted"})
		return {"state": "todo" if n else "ok", "text": _("{0} waiting for review").format(n)}
	if key == "wikidata":
		n = _count("RD Creator", {"match_status": "Proposed"}) + _count(
			"RD Subject", {"match_status": "Proposed"}
		)
		return (
			{"state": "todo", "text": _("{0} matches to review").format(n)}
			if n
			else {"state": "ok", "text": _("Nothing waiting")}
		)
	if c.urls and not c.actions:
		return {"state": "ok", "text": _("Available")}
	return {"state": "info", "text": _("On")}


@frappe.whitelist()
def overview() -> list[dict]:
	"""The groups of connections with, for each, its status and what this person may do."""
	frappe.only_for(core.WORKERS)
	roles = set(frappe.get_roles())
	from sok_resdesk.catalogue import base_url

	base = base_url().rstrip("/")
	out = []
	for g in core.GROUPS:
		cards = []
		for c in (x for x in core.CARDS if x.group == g.key):
			cards.append(
				{
					"key": c.key,
					"title": _(c.title),
					"what": _(c.what),
					"who": _(c.who),
					"status": _status(c),
					"can": core.can_use(c, roles),
					"feature": c.feature,
					"actions": [
						{
							"label": _(a.label),
							"kind": a.kind,
							"target": list(a.target) if isinstance(a.target, tuple) else a.target,
							"primary": a.primary,
						}
						for a in c.actions
					],
					"urls": [{"label": _(label), "url": base + path} for label, path in c.urls],
				}
			)
		out.append({"key": g.key, "title": _(g.title), "what": _(g.what), "icon": g.icon, "cards": cards})
	return out
