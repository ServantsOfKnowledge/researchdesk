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


def public_telegram_link() -> str:
	"""The Message us on Telegram link for the Contact us page: the library's own public username, or ''
	when none is set. Never in Classified mode, which sends no one to an outside service."""
	if seams.classified():
		return ""
	return rules.telegram_link(settings().get("telegram_username"))


def validate_settings(doc) -> None:
	"""RD Settings: the public Telegram name is saved in its plain form, or refused."""
	name = (doc.get("telegram_username") or "").strip()
	if not name:
		return
	if not rules.clean_username(name):
		frappe.throw(
			_(
				"The Telegram username must be 5 to 32 letters, digits or underscores, starting with a letter (like SOKLibrary)."
			)
		)
	doc.telegram_username = rules.clean_username(name)


def telegram_ready() -> bool:
	"""Token and chat ID are both set (RD Settings), and Classified mode is not on."""
	if seams.classified():
		return False
	s = settings()
	return bool(
		(s.get_password("telegram_bot_token", raise_exception=False) or "").strip()
		and (s.get("telegram_chat_id") or "").strip()
	)


def _telegram_call(method: str, payload: dict) -> tuple[bool, int, dict, str]:
	"""(reached and answered 200, status, answer, why not) for one Telegram Bot API call with the saved
	token. The token is in the address, so nothing here ever logs or returns the text of an error, only
	its kind."""
	token = (settings().get_password("telegram_bot_token", raise_exception=False) or "").strip()
	if not token:
		return False, 0, {}, _("Enter the bot token first, and save Settings.")
	if not rules.looks_like_token(token):  # also keeps a stray "/" or "?" out of the address
		return (
			False,
			0,
			{},
			_("That does not look like a bot token. It is a number, a colon and a long string."),
		)
	try:
		resp = requests.post(
			f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=10, allow_redirects=False
		)
	except Exception as e:
		frappe.log_error(title="Research Desk: the Telegram alert failed", message=type(e).__name__)
		return False, 0, {}, rules.telegram_problem(0)
	try:
		data = resp.json() or {}
	except Exception:
		data = {}
	if resp.status_code == 200:
		return True, 200, data, ""
	frappe.log_error(
		title="Research Desk: the Telegram alert was refused", message=f"Telegram answered {resp.status_code}"
	)
	return (
		False,
		resp.status_code,
		data,
		rules.telegram_problem(resp.status_code, data.get("description", "")),
	)


def _send_telegram(text: str) -> tuple[bool, str]:
	"""(sent, why not): one message to the chat in RD Settings."""
	chat = (settings().get("telegram_chat_id") or "").strip()
	if not chat:
		return False, _("Enter the bot token and the chat ID first, and save Settings.")
	ok, _status, _data, why = _telegram_call(
		"sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": True}
	)
	return ok, why


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=600)
def find_telegram_chat() -> dict:
	"""Settings → Find the Chat ID: the chats the bot has heard from, so no one has to read Telegram's
	address in a browser. {"ok", "chats": [{"id", "label"}], "why"}."""
	frappe.only_for(connections.MANAGERS)
	if seams.classified():
		return {"ok": False, "chats": [], "why": _("Telegram is not used in Classified mode.")}
	ok, _status, data, why = _telegram_call("getUpdates", {"limit": 100, "timeout": 0})
	if not ok:
		return {"ok": False, "chats": [], "why": why}
	chats = rules.chats_from_updates(data)
	if not chats:
		return {
			"ok": False,
			"chats": [],
			"why": _(
				"The bot has heard from no one yet. Open your bot in Telegram, press Start and write 'hello' (for a group: add the bot and write there), then try again."
			),
		}
	return {"ok": True, "chats": chats, "why": ""}


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
