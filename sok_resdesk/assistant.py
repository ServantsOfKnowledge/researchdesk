"""The optional language model (Settings → Assistant): one small model, local or hosted, that suggests.

It runs only where an admin switched it on, only for the uses they ticked, and only ever drafts: what it
says goes to the same checking screens as everything else read from a book, and every answer is checked
against the page text first (core/llm.py). Local servers (Ollama, llama.cpp, vLLM) and hosted services
share one protocol: OpenAI-style chat completions. Book text goes to a hosted service only when the admin
chose Hosted API.
"""

from __future__ import annotations

import frappe
import requests
from frappe import _

from sok_resdesk import access
from sok_resdesk.core import llm, netguard

TIMEOUT = 120  # seconds: a small model on a CPU takes a while


def _settings():
	return frappe.get_cached_doc("RD Settings")


def provider() -> str:
	return _settings().get("assistant_provider") or "Off"


def enabled(use: str) -> bool:
	"""Whether the assistant is on, set up, and ticked for this use (titles, contents, subjects, search)."""
	s = _settings()
	return (
		provider() != "Off"
		and bool((s.get("assistant_url") or "").strip())
		and bool((s.get("assistant_model") or "").strip())
		and bool(s.get(f"assistant_{use}"))
	)


def ask(system: str, user: str, max_tokens: int = 600) -> str:
	"""The model's reply text, or "" when it cannot be reached (it is only ever a help, never needed)."""
	s = _settings()
	base = (s.get("assistant_url") or "").strip().rstrip("/")
	url = f"{base}/chat/completions"
	headers = {"Content-Type": "application/json"}
	key = (s.get_password("assistant_key", raise_exception=False) or "").strip()
	if key:
		headers["Authorization"] = f"Bearer {key}"
	try:
		# a local server is the library's own machine; a hosted one must be a public address
		trusted = (requests.utils.urlparse(url).hostname or "",) if provider() == "Local server" else ()
		netguard.check(url, trusted)
		r = requests.post(
			url,
			json=llm.chat_payload(s.assistant_model.strip(), system, user, max_tokens),
			headers=headers,
			timeout=TIMEOUT,
			allow_redirects=False,
		)
		return llm.reply_text(r.json()) if r.ok else ""
	except (requests.RequestException, netguard.Blocked, ValueError):
		frappe.log_error(title="Research Desk: the assistant could not be reached")
		return ""


@frappe.whitelist(methods=["POST"])
def test() -> dict:
	"""Ask the model a trivial question, to show the admin whether Settings → Assistant works."""
	if not access.is_admin():
		frappe.throw(_("Only managers can test the assistant."), frappe.PermissionError)
	if provider() == "Off":
		return {"ok": 0, "message": _("The assistant is switched off.")}
	reply = ask("Reply with the single word: ready", "Are you there?", 10)
	if reply.strip():
		return {"ok": 1, "message": _("It answered: {0}").format(reply.strip()[:80])}
	return {"ok": 0, "message": _("No answer. Check the address, the model name and the key; see Error Log.")}
