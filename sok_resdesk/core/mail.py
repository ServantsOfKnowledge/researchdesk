"""Pure helpers for outgoing email set-up: provider presets, input checks, plain-words errors."""

from __future__ import annotations

import re

# (label, server, port, security) for the choices most libraries make
PRESETS = [
	{
		"label": "Resend (login is 'resend', password is your API key)",
		"server": "smtp.resend.com",
		"port": 587,
		"security": "tls",
		"login": "resend",
	},
	{
		"label": "Gmail / Google Workspace (use an app password)",
		"server": "smtp.gmail.com",
		"port": 587,
		"security": "tls",
	},
	{"label": "Microsoft 365 / Outlook", "server": "smtp.office365.com", "port": 587, "security": "tls"},
	{"label": "Zoho Mail", "server": "smtp.zoho.com", "port": 587, "security": "tls"},
	{
		"label": "Amazon SES (region server)",
		"server": "email-smtp.ap-south-1.amazonaws.com",
		"port": 587,
		"security": "tls",
	},
	{"label": "Brevo (Sendinblue)", "server": "smtp-relay.brevo.com", "port": 587, "security": "tls"},
	{"label": "Another server", "server": "", "port": 587, "security": "tls"},
]

SECURITY = ("tls", "ssl", "none")
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_KNOWN = (
	(
		"535",
		"The mailbox name or password was refused. For Gmail and Microsoft use an app password, not the normal one.",
	),
	(
		"authentication",
		"The mailbox name or password was refused. For Gmail and Microsoft use an app password, not the normal one.",
	),
	("username and password not accepted", "The mailbox name or password was refused. Use an app password."),
	(
		"name or service not known",
		"The mail server's name could not be found. Check the spelling of the server.",
	),
	("getaddrinfo", "The mail server's name could not be found. Check the spelling of the server."),
	(
		"timed out",
		"The mail server did not answer. Check the server and port, and that this machine may reach it.",
	),
	("connection refused", "The mail server refused the connection. Check the port and the security choice."),
	(
		"wrong version number",
		"The security choice does not match the port: try STARTTLS on 587, or SSL on 465.",
	),
	("starttls", "The server does not offer STARTTLS on this port: try SSL on 465, or none on 25."),
	("sender address rejected", "The server will not send as this address. Use the mailbox's own address."),
	("relay access denied", "The server will not relay for this address. Sign in with a real mailbox."),
)


def problem(email_id: str, server: str, port, security: str) -> str:
	"""A sentence about what is wrong with the form, or ''."""
	if not _ADDRESS.match((email_id or "").strip()):
		return "Enter the address emails will come from, like library@example.org."
	if not (server or "").strip() or " " in server.strip():
		return "Enter the mail (SMTP) server, like smtp.example.org."
	try:
		p = int(port)
	except (TypeError, ValueError):
		return "The port is a number, usually 587 or 465."
	if not 1 <= p <= 65535:
		return "The port is a number, usually 587 or 465."
	if security not in SECURITY:
		return "Choose STARTTLS, SSL or none."
	return ""


def plain_error(raw: str) -> str:
	"""The mail library's message in words a librarian can act on; the raw text if unknown."""
	text = (raw or "").strip()
	if not text:
		return ""
	low = text.lower()
	for needle, words in _KNOWN:
		if needle in low:
			return words
	return text.splitlines()[-1][:240]
