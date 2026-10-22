"""Messages from people who visit the portal: what is accepted, and what is said to the Desk's alert.

Pure Python (no Frappe), so it is unit-tested. sok_resdesk/contact.py applies it.
"""

from __future__ import annotations

import re

MAX_NAME = 140
MAX_CONTACT = 140
MIN_MESSAGE = 10
MAX_MESSAGE = 2000
FLOOD_PER_HOUR = 60  # all visitors together: past this the form asks people to come back later

_TAGS = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _plain(text, limit: int, keep_lines: bool = False) -> str:
	text = _CONTROL.sub("", _TAGS.sub("", str(text or "")))
	if not keep_lines:
		text = " ".join(text.split())
	else:
		text = "\n".join(" ".join(line.split()) for line in text.replace("\r", "").split("\n")).strip()
		text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()[:limit]


def clean(name, contact, message, trap="") -> tuple[dict | None, str]:
	"""(the fields to keep, "") or (None, why): why is "trap" (a robot filled the hidden field: say
	nothing), "short" or "empty" (no message of any use)."""
	if str(trap or "").strip():
		return None, "trap"
	body = _plain(message, MAX_MESSAGE, keep_lines=True)
	if not body:
		return None, "empty"
	if len(body) < MIN_MESSAGE:
		return None, "short"
	return {
		"full_name": _plain(name, MAX_NAME),
		"contact": _plain(contact, MAX_CONTACT),
		"message": body,
	}, ""


def too_many(count_last_hour: int, cap: int = FLOOD_PER_HOUR) -> bool:
	return count_last_hour >= cap


def alert_text(portal: str, url: str) -> str:
	"""What Telegram is told: that a message came and where to read it, never the message itself."""
	return f"{portal}: a visitor sent a message. Read it in the Desk: {url}"


_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")


def looks_like_token(token: str) -> bool:
	"""A Telegram bot token is a number, a colon and a long string, like 123456789:AAH-xyz…"""
	return bool(_TOKEN.match((token or "").strip()))


def test_text(portal: str) -> str:
	return f"{portal}: the Telegram alert works. You will get a message like this when a visitor writes."


def telegram_problem(status: int, description: str = "") -> str:
	"""Telegram's refusal in plain words, with what to do. `status` 0 means Telegram was not reached."""
	said = (description or "").lower()
	if status == 0:
		return (
			"Telegram could not be reached from this server. Check that it can open https://api.telegram.org."
		)
	if status == 401 or status == 404:
		return "Telegram does not accept this bot token. Copy it again from @BotFather."
	if status == 403:
		return "The bot cannot write to that chat: it was blocked or removed. Open the chat, press Start, and try again."
	if status == 400 and "chat not found" in said:
		return "Telegram does not know that chat ID. Write any message to your bot first, then read the id again."
	if status == 429:
		return "Telegram asks us to slow down. Try again in a minute."
	return f"Telegram refused the message (code {status}). Check the token and the chat ID."


def clean_username(name) -> str:
	"""A Telegram username as people write it (`@name`, `t.me/name` or `https://t.me/name`), or "" if it
	is not one: 5 to 32 letters, digits or underscores, starting with a letter."""
	text = str(name or "").strip()
	for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
		if text.lower().startswith(prefix):
			text = text[len(prefix) :]
	text = text.strip("/ ")
	return text if _NAME.match(text) else ""


def telegram_link(name) -> str:
	user = clean_username(name)
	return f"https://t.me/{user}" if user else ""


def chats_from_updates(data) -> list[dict]:
	"""The chats a bot has heard from, newest first, from Telegram's getUpdates answer:
	[{"id": "123", "label": "Asha (private chat)"}]. Used to find the Chat ID without a browser."""
	seen, out = set(), []
	for update in reversed((data or {}).get("result") or []):
		for key in ("message", "edited_message", "channel_post", "my_chat_member"):
			chat = (update.get(key) or {}).get("chat")
			if not chat or chat.get("id") in seen:
				continue
			seen.add(chat["id"])
			kind = {
				"private": "private chat",
				"group": "group",
				"supergroup": "group",
				"channel": "channel",
			}.get(chat.get("type"), "chat")
			name = (
				chat.get("title")
				or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x)
				or (f"@{chat['username']}" if chat.get("username") else "")
			)
			out.append({"id": str(chat["id"]), "label": f"{name or 'No name'} ({kind})"})
	return out
