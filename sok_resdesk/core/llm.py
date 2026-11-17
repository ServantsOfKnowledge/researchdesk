"""Talking to a language model, as pure rules: the request, reading the reply, and refusing what the
page does not support. A model only ever suggests; every suggestion is checked here, then by a person.
"""

from __future__ import annotations

import json
import re

from sok_resdesk.core import frontmatter

PROVIDERS = ("Off", "Local server", "Hosted API")
USES = ("titles", "contents", "subjects", "search")
MAX_PAGE_CHARS = 6000  # of page text sent in one request


def chat_payload(model: str, system: str, user: str, max_tokens: int = 600) -> dict:
	"""An OpenAI-style chat request (Ollama, llama.cpp, vLLM, OpenRouter, OpenAI and Anthropic all take it)."""
	return {
		"model": model,
		"temperature": 0,
		"max_tokens": max_tokens,
		"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
	}


def reply_text(data) -> str:
	try:
		return str(data["choices"][0]["message"]["content"] or "")
	except (KeyError, IndexError, TypeError):
		return ""


def parse_json(text: str):
	"""The first JSON object in a reply, however it is wrapped in prose or code fences; None if none."""
	text = re.sub(r"```(?:json)?", "", text or "")
	start = text.find("{")
	while start != -1:
		try:
			value, _end = json.JSONDecoder().raw_decode(text[start:])
			return value if isinstance(value, dict) else None
		except ValueError:
			start = text.find("{", start + 1)
	return None


def _norm(text) -> str:
	return re.sub(r"[\W_]+", "", str(text or "").casefold())


def front_prompt(pages: list[dict], missing: list[str]) -> tuple[str, str]:
	"""(system, user) asking only for the `missing` details of a book, from its first pages."""
	text = "\n\n".join(f"[page {p['leaf'] + 1}]\n{p.get('text') or ''}" for p in pages)[:MAX_PAGE_CHARS]
	system = (
		"You read the OCR text of a book's title page and imprint page. Reply with one JSON object only, "
		f"with these keys: {', '.join(missing)}. Use exactly the words printed on the page; use null for "
		"anything not printed. publisher is the publishing house, place the city of publication, year the "
		"year of publication as four digits, isbn the ISBN as printed. Never guess."
	)
	return system, text


def front_details(reply: str, pages: list[dict], current: dict) -> list[dict]:
	"""Details from a model's reply that the pages really support, in core/frontmatter.read's form.

	A value is kept only if it passes the same checks as one read by rules (a year in range, an ISBN with
	its check digit) and is printed on the pages the model was given, so a guess is dropped."""
	data = parse_json(reply) or {}
	source = _norm(" ".join(p.get("text") or "" for p in pages))
	where = {_norm(p.get("text")): p["leaf"] for p in pages}
	out = []
	for field in frontmatter.FIELDS:
		value = data.get(field)
		if value in (None, "", "null"):
			continue
		value = re.sub(r"\s+", " ", str(value)).strip()
		if field == "year" and not frontmatter._year_ok(value):
			continue
		if field == "isbn" and not frontmatter.valid_isbn(value):
			continue
		if field in ("publisher", "place") and not frontmatter._clean(value):
			continue
		if _norm(value) not in source or not frontmatter.is_new(field, value, current.get(field)):
			continue
		leaf = next((lf for text, lf in where.items() if _norm(value) in text), pages[0]["leaf"])
		line = next(
			(
				ln.strip()
				for p in pages
				if p["leaf"] == leaf
				for ln in (p.get("text") or "").splitlines()
				if _norm(value) in _norm(ln)
			),
			"",
		)
		out.append({"field": field, "value": value, "leaf": leaf, "snippet": line[:160], "confidence": 0.5})
	return out
