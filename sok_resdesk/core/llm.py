"""Talking to a language model, as pure rules: the request, reading the reply, and refusing what the
page does not support. A model only ever suggests; every suggestion is checked here, then by a person.
"""

from __future__ import annotations

import json
import re

from sok_resdesk.core import contents, frontmatter

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


def contents_prompt(texts: list[str]) -> tuple[str, str]:
	"""(system, user) asking for the table of contents on these OCR pages."""
	system = (
		"You read the OCR text of the contents pages of a book. Reply with one JSON object only: "
		'{"entries": [{"title": "...", "page": "12", "level": 1}]}. One entry per heading, in order, with its '
		"printed page number as printed (digits or roman numerals) and level 1 for a chapter, 2 for a section "
		"in it. Use the words printed on the page; mend only obvious OCR slips. If there is no table of "
		'contents, reply {"entries": []}.'
	)
	return system, "\n\n".join(texts)[:MAX_PAGE_CHARS]


def contents_entries(reply: str, text: str) -> list[dict]:
	"""Entries from a model's reply, in core/contents.parse's form, that the pages support: each has a
	printed page (digits or roman) and a title whose start is printed on the pages it was given."""
	data = parse_json(reply) or {}
	source = _norm(text)
	out = []
	for e in data.get("entries") if isinstance(data.get("entries"), list) else []:
		if not isinstance(e, dict):
			continue
		title = re.sub(r"\s+", " ", str(e.get("title") or "")).strip()
		page = contents.digits(str(e.get("page") or "").strip().lower())
		if not title or not (page.isdigit() or contents.ROMAN.match(page)):
			continue
		if _norm(title)[:12] not in source:
			continue
		try:
			level = min(max(int(e.get("level") or 1), 1), 4)
		except (TypeError, ValueError):
			level = 1
		out.append({"title": title, "page": page, "level": level})
	return out


DESCRIBE = ("subjects", "summary", "item_type")
SAMPLE_PAGES = 12  # of the first pages, the text a book is described from
MAX_SUBJECTS = 6


def describe_prompt(book: dict, pages: list[dict], types: list[str]) -> tuple[str, str]:
	"""(system, user) asking for subjects, a short summary and the document type of a book."""
	system = (
		"You help a librarian describe a book from its title and the first pages of its OCR text. Reply with "
		'one JSON object only: {"subjects": ["..."], "summary": "...", "item_type": "..."}. subjects: at most '
		f"{MAX_SUBJECTS} short subject headings (a topic, place, period or tradition), in the language of the "
		"book's own catalogue where it is English, else in English. summary: two plain sentences saying what "
		f"the book is about, no praise. item_type: one of {', '.join(types)}. Say only what the text supports; "
		"use null or an empty list when unsure."
	)
	head = f"Title: {book.get('title') or ''}\nAuthor: {book.get('creators') or ''}\nLanguage: {book.get('language') or ''}"
	text = "\n\n".join((p.get("text") or "") for p in pages[:SAMPLE_PAGES])
	return system, f"{head}\n\n{text}"[:MAX_PAGE_CHARS]


def describe_details(reply: str, current: dict, types: list[str]) -> list[dict]:
	"""Details from a model's reply worth offering a person: subjects the book lacks (joined with "; "), a
	summary only for a book with no description, and a document type that differs from the book's. They
	are suggestions, not facts from the page, so they carry a low confidence and no page."""
	data = parse_json(reply) or {}
	out = []

	def add(field: str, value: str) -> None:
		out.append({"field": field, "value": value, "leaf": None, "snippet": "", "confidence": 0.4})

	have = {_norm(s) for s in re.split(r";", str(current.get("subjects") or ""))}
	raw = data.get("subjects") if isinstance(data.get("subjects"), list) else []
	subjects = []
	for s in raw:
		s = re.sub(r"[;\s]+", " ", str(s or "")).strip(" .,")
		if 2 <= len(s) <= 60 and _norm(s) not in have and _norm(s) not in {_norm(x) for x in subjects}:
			subjects.append(s)
	if subjects:
		add("subjects", "; ".join(subjects[:MAX_SUBJECTS]))
	summary = re.sub(r"\s+", " ", str(data.get("summary") or "")).strip()
	if 20 <= len(summary) <= 600 and not str(current.get("summary") or "").strip():
		add("summary", summary)
	kind = str(data.get("item_type") or "").strip()
	if kind in types and kind != current.get("item_type"):
		add("item_type", kind)
	return out
