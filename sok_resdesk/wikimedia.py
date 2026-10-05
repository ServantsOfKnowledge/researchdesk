"""Each person's own Wikimedia account (Desk → My Wikimedia Account).

What Research Desk gives back to Wikidata and Wikisource is sent under the account of the person
who sends it, so Wikimedia's histories credit them and its rules (no shared accounts; a page is
validated by someone other than its proofreader) hold. A person connects once by pasting an
**OAuth 2.0 access token** from an *owner-only* consumer they register at meta.wikimedia.org
(no approval wait; it works on every Wikimedia wiki). The token is kept encrypted, belongs to its
person alone, and is used only for edits they ask for. A System Manager cannot read or use it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from sok_resdesk.core import wikimedia as wm

WORKERS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer", "ResDesk Proofreader")
DOCTYPE = "RD Wikimedia Account"
STEPS = [
	"Open the Wikimedia registration page (the link below) while logged in to your Wikimedia account.",
	"Propose an OAuth 2.0 consumer. Tick “This consumer is for use only by” followed by your own Wikimedia username (owner-only: no approval needed).",
	"Under grants choose “Edit existing pages” and “Create, edit, and move pages”; for Wikisource work that is all.",
	"Submit. Wikimedia shows the consumer's **access token**: copy it here, under Connect.",
]


def _account(user: str):
	return frappe.get_doc(DOCTYPE, user) if frappe.db.exists(DOCTYPE, user) else None


@frappe.whitelist()
def status() -> dict:
	"""My connection: whether, as whom and since when. The token is never sent to the browser."""
	frappe.only_for(WORKERS)
	acc = _account(frappe.session.user)
	return {
		"connected": bool(acc and acc.wikimedia_user),
		"wikimedia_user": acc.wikimedia_user if acc else "",
		"connected_on": str(acc.connected_on or "") if acc else "",
		"last_used": str(acc.last_used or "") if acc else "",
		"note": acc.note if acc else "",
		"register_url": wm.REGISTER,
		"steps": [_(s) for s in STEPS],
	}


@frappe.whitelist(methods=["POST"])
def connect(token: str) -> dict:
	"""Check the access token with Wikimedia, then keep it (encrypted) for this person."""
	frappe.only_for(WORKERS)
	token = (token or "").strip()
	if len(token) < 20:
		frappe.throw(_("Paste the whole access token that Wikimedia showed."))
	client = wm.WikimediaClient(wm.META_API, token)
	try:
		who = client.whoami()
	except wm.WikimediaError as e:
		frappe.throw(_("Wikimedia did not accept the token: {0}").format(str(e)[:300]))
	lacks = [r for r in wm.NEEDED if r not in set(who["rights"])]
	if lacks:
		frappe.throw(
			_(
				"The token is not allowed to {0}: register it again with “Edit existing pages” granted."
			).format(", ".join(lacks))
		)
	note = ", ".join(
		sorted(r for r in who["rights"] if r.startswith(("edit", "createpage", "move", "upload")))
	)
	user = frappe.session.user
	acc = _account(user) or frappe.new_doc(DOCTYPE)
	acc.user = user
	acc.wikimedia_user = who["name"]
	acc.connected_on = now_datetime()
	acc.token = token
	acc.note = note
	acc.flags.ignore_permissions = True
	acc.save() if not acc.is_new() else acc.insert()
	return status()


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	"""Forget my token (revoke the consumer at Wikimedia too, if you want it unusable there)."""
	frappe.only_for(WORKERS)
	if frappe.db.exists(DOCTYPE, frappe.session.user):
		frappe.delete_doc(DOCTYPE, frappe.session.user, ignore_permissions=True)
	return status()


def token_for(user: str) -> str:
	"""This person's access token, or '' when they have not connected one."""
	acc = _account(user)
	return (acc.get_password("token", raise_exception=False) or "") if acc else ""


def connected(user: str | None = None) -> bool:
	return bool(token_for(user or frappe.session.user))


def need_account(user: str | None = None) -> str:
	"""The token to send edits as this person, or a plain explanation of what to do first."""
	token = token_for(user or frappe.session.user)
	if not token:
		frappe.throw(
			_("Connect your own Wikimedia account first (Research Desk → My Wikimedia Account)."),
			title=_("Not connected"),
		)
	return token


def touch(user: str) -> None:
	"""Remember that the account was used (shown on My Wikimedia Account)."""
	if frappe.db.exists(DOCTYPE, user):
		frappe.db.set_value(DOCTYPE, user, "last_used", now_datetime(), update_modified=False)
