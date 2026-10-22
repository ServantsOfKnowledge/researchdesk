"""Messages from people who visit: a public form, an inbox in the Desk, an optional Telegram alert.

The form is the only way in (RD Message cannot be made by a guest any other way). A message is kept in
the Desk, so nothing is lost if Telegram is down; Telegram is told only that one came, with a link.
"""

from __future__ import annotations

import frappe
import requests
from frappe import _
from frappe.utils import add_days, add_to_date, cint, now_datetime

from sok_resdesk import access, seams
from sok_resdesk.catalogue import base_url, portal_title, settings
from sok_resdesk.core import connections
from sok_resdesk.core import contact as rules
from sok_resdesk.ratelimit import rate_limit

DOCTYPE = "RD Message"
KEEP_DAYS = 365


def enabled() -> bool:
	"""The Contact us page and its form are on unless RD Settings turns them off. They are never on in
	Classified mode, and a guest cannot use them where the library asks people to sign in."""
	if seams.classified():
		return False
	if access.viewer().get("login_required"):
		return False
	value = settings().get("contact_enabled")
	return value in (None, "") or bool(cint(value))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=8, seconds=3600)
def send(full_name: str = "", contact: str = "", message: str = "", rd_hp: str = "") -> dict:
	"""A visitor's message. `rd_hp` is a field people cannot see; a robot fills it."""
	if not enabled():
		frappe.throw(_("The library is not taking messages here."))
	fields, why = rules.clean(full_name, contact, message, rd_hp)
	if why == "trap":
		return {"sent": 1}  # looks like success to a robot, and nothing is kept
	if why:
		frappe.throw(
			_("Please write a message.")
			if why == "empty"
			else _("Please write a little more: a sentence or two.")
		)
	recent = frappe.db.count(
		DOCTYPE, {"creation": (">", add_to_date(now_datetime(), hours=-1)), "status": ("!=", "Spam")}
	)
	if rules.too_many(recent):
		frappe.throw(_("Many messages are arriving just now. Please try again in an hour."))
	doc = frappe.get_doc({"doctype": DOCTYPE, **fields})
	doc.flags.ignore_permissions = True
	doc.insert()
	return {"sent": 1}


def after_message(doc) -> None:
	"""A new message: a Desk alert for the managers, and Telegram if it is set up."""
	access.notify_managers(doc, _("A visitor sent the library a message"))
	frappe.enqueue(
		"sok_resdesk.contact.tell_telegram", name=doc.name, queue="short", enqueue_after_commit=True
	)


def telegram_ready() -> bool:
	"""Token and chat ID are both set (RD Settings), and Classified mode is not on."""
	if seams.classified():
		return False
	s = settings()
	return bool(
		(s.get_password("telegram_bot_token", raise_exception=False) or "").strip()
		and (s.get("telegram_chat_id") or "").strip()
	)


def _send_telegram(text: str) -> tuple[bool, str]:
	"""(sent, why not): one message to the chat in RD Settings. The token is in the address, so nothing
	here ever logs or returns the text of an error, only its kind."""
	s = settings()
	token = (s.get_password("telegram_bot_token", raise_exception=False) or "").strip()
	chat = (s.get("telegram_chat_id") or "").strip()
	if not token or not chat:
		return False, _("Enter the bot token and the chat ID first, and save Settings.")
	if not rules.looks_like_token(token):  # also keeps a stray "/" or "?" out of the address
		return False, _("That does not look like a bot token. It is a number, a colon and a long string.")
	try:
		resp = requests.post(
			f"https://api.telegram.org/bot{token}/sendMessage",
			json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
			timeout=10,
			allow_redirects=False,
		)
	except Exception as e:
		frappe.log_error(title="Research Desk: the Telegram alert failed", message=type(e).__name__)
		return False, rules.telegram_problem(0)
	if resp.status_code == 200:
		return True, ""
	try:
		said = (resp.json() or {}).get("description", "")
	except Exception:
		said = ""
	frappe.log_error(
		title="Research Desk: the Telegram alert was refused", message=f"Telegram answered {resp.status_code}"
	)
	return False, rules.telegram_problem(resp.status_code, said)


def tell_telegram(name: str) -> None:
	"""A new message: one private Telegram message, if set up. Never breaks the visitor's message, and
	never in Classified mode, which allows no outside connection."""
	if seams.classified():
		return
	_send_telegram(rules.alert_text(portal_title(), f"{base_url()}/app/rd-message/{name}"))


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=600)
def test_telegram() -> dict:
	"""Settings → Send a Test Telegram Message: {"ok", "why"} in plain words."""
	frappe.only_for(connections.MANAGERS)
	if seams.classified():
		return {"ok": False, "why": _("Telegram is not used in Classified mode.")}
	ok, why = _send_telegram(rules.test_text(portal_title()))
	return {"ok": ok, "why": why}


def purge_old() -> int:
	"""Daily: messages older than RD Settings → days to keep are deleted (0 keeps them all)."""
	days = settings().get("contact_keep_days")
	days = KEEP_DAYS if days in (None, "") else cint(days)
	if days <= 0:
		return 0
	old = frappe.get_all(DOCTYPE, filters={"creation": ("<", add_days(now_datetime(), -days))}, pluck="name")
	for name in old:
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True, delete_permanently=True)
	return len(old)
