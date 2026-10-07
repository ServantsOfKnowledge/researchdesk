"""Outgoing email: the sign-in, sign-up and password emails need it.

Frappe sends every one of those through an outgoing Email Account. A fresh install has none, so
"send me a login link" and the sign-up confirmation quietly go nowhere. This module is the one
place managers set it up (Connections → Outgoing email), test it, and see what is stuck.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core import mail as core

MANAGERS = ("System Manager", "SOK Super Admin", "ResDesk Manager")
ACCOUNT = "Research Desk"


def outgoing_account() -> str | None:
	"""The Email Account that sends mail now (the default outgoing one), or None."""
	for filters in ({"enable_outgoing": 1, "default_outgoing": 1}, {"enable_outgoing": 1}):
		name = frappe.db.get_value("Email Account", filters, "name")
		if name:
			return name
	return None


def ready() -> bool:
	return bool(outgoing_account())


def stuck() -> dict:
	"""Emails waiting or failed in Frappe's queue: {waiting, failed, last_error}."""
	try:
		waiting = frappe.db.count("Email Queue", {"status": "Not Sent"})
		failed = frappe.db.count("Email Queue", {"status": "Error"})
		last = frappe.db.get_value("Email Queue", {"status": "Error"}, "error", order_by="modified desc")
	except Exception:
		return {"waiting": 0, "failed": 0, "last_error": ""}
	return {"waiting": waiting, "failed": failed, "last_error": core.plain_error(last or "")}


def signup_mode() -> str:
	from sok_resdesk.catalogue import settings

	return settings().reader_signup or "Admins add readers"


@frappe.whitelist()
def status() -> dict:
	frappe.only_for(MANAGERS)
	name = outgoing_account()
	acc = (
		frappe.db.get_value(
			"Email Account",
			name,
			["email_id", "smtp_server", "smtp_port", "login_id", "use_tls", "use_ssl_for_outgoing"],
			as_dict=True,
		)
		if name
		else None
	) or {}
	return {
		"ready": bool(name),
		"account": name,
		"settings": acc,
		"presets": core.PRESETS,
		"signup": signup_mode(),
		"needs_email": signup_mode() != "Admins add readers",
		**stuck(),
	}


@frappe.whitelist()
def save(
	email_id: str,
	smtp_server: str,
	smtp_port: int | str = 587,
	login_id: str = "",
	password: str = "",
	security: str = "tls",
) -> dict:
	"""Create or update the Research Desk outgoing account and make it the default."""
	frappe.only_for(MANAGERS)
	problem = core.problem(email_id, smtp_server, smtp_port, security)
	if problem:
		frappe.throw(_(problem))
	port, tls, ssl = cint(smtp_port), security == "tls", security == "ssl"
	try:
		doc = _save_account(email_id, smtp_server, port, login_id, password, tls, ssl)
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="Research Desk: outgoing email could not be saved")
		frappe.throw(
			_("Could not save the email settings: {0}").format(core.plain_error(str(e)) or type(e).__name__)
		)
	frappe.db.commit()
	return {"saved": True, "account": doc.name}


def _save_account(email_id, smtp_server, port, login_id, password, tls, ssl):
	existing = frappe.db.exists("Email Account", ACCOUNT)
	doc = frappe.get_doc("Email Account", ACCOUNT) if existing else frappe.new_doc("Email Account")
	doc.update(
		{
			"email_account_name": ACCOUNT,
			"email_id": email_id.strip(),
			"smtp_server": smtp_server.strip(),
			"smtp_port": port,
			"use_tls": 1 if tls else 0,
			"use_ssl_for_outgoing": 1 if ssl else 0,
			"login_id_is_different": 1 if login_id.strip() else 0,
			"login_id": login_id.strip(),
			"enable_outgoing": 1,
			"default_outgoing": 1,
			"enable_incoming": 0,
			"always_use_account_email_id_as_sender": 1,
			"send_unsubscribe_message": 0,
			"add_signature": 0,
		}
	)
	if password:
		doc.password = password
	elif not existing:
		frappe.throw(_("Enter the password (or app password) for this mailbox."))
	# Frappe re-saves (and so re-validates, with a live SMTP login) every other default account
	# when this one becomes the default: one old account with a bad setting would then fail the
	# whole save. Take the default off the others quietly first.
	for other in frappe.get_all(
		"Email Account", filters={"default_outgoing": 1, "name": ("!=", ACCOUNT)}, pluck="name"
	):
		frappe.db.set_value("Email Account", other, "default_outgoing", 0, update_modified=False)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate = True  # we test the real thing ourselves, with a clear message
	doc.save() if existing else doc.insert()
	return doc


@frappe.whitelist()
def test(to: str = "") -> dict:
	"""Send a real test email now and say, in plain words, what went wrong if it did."""
	frappe.only_for(MANAGERS)
	to = (to or frappe.db.get_value("User", frappe.session.user, "email") or "").strip()
	if "@" not in to:
		frappe.throw(_("Give an address to send the test to."))
	if not ready():
		frappe.throw(_("Set up outgoing email first."))
	try:
		frappe.sendmail(
			recipients=[to],
			subject=_("Test email from Research Desk"),
			message=_(
				"<p>If you can read this, sign-in and sign-up emails from this library will arrive.</p>"
			),
			now=True,
		)
	except Exception as e:
		frappe.log_error(title="Research Desk: test email failed")
		return {"ok": False, "message": core.plain_error(str(e)) or type(e).__name__}
	return {"ok": True, "message": _("Sent to {0}. Check that inbox (and its spam folder).").format(to)}


@frappe.whitelist()
def retry_failed() -> dict:
	"""Put failed emails back in the queue and send them now."""
	frappe.only_for(MANAGERS)
	frappe.db.sql("update `tabEmail Queue` set status = 'Not Sent' where status = 'Error'")
	frappe.db.commit()
	try:
		from frappe.email.queue import flush

		flush()
	except Exception as e:
		return {"message": core.plain_error(str(e))}
	left = stuck()
	return {"message": _("{0} emails still waiting or failed.").format(left["waiting"] + left["failed"])}
