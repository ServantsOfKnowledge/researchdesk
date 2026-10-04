"""The portal's phrases, for translating it: found in the app's templates, scripts and Python, and
kept as a spreadsheet (one row per phrase, one column per language). Pure Python.

Templates and Python mark a phrase as ``_("…")``, the portal's scripts as ``__("…")``, as
Frappe does. Phrases with ``{0}``, ``{1}`` keep those places: a translation moves them where
the language needs them (``{0} books`` → ``{0} ಪುಸ್ತಕಗಳು``).
"""

from __future__ import annotations

import csv
import io
import re

# _("…") / _('…') in Jinja and Python; __("…") / __('…') in JavaScript. A string ends at its own
# unescaped quote; f-strings and concatenations are not phrases and are left out.
_PY = re.compile(r"""(?<![\w.])_\(\s*(?P<q>["'])(?P<s>(?:\\.|(?!(?P=q)).)+?)(?P=q)\s*[,)]""", re.S)
_JS = re.compile(r"""(?<![\w.$])__\(\s*(?P<q>["'])(?P<s>(?:\\.|(?!(?P=q)).)+?)(?P=q)\s*[,)]""", re.S)
_ESC = re.compile(r"\\(.)")
PLACES = re.compile(r"\{\d+\}")


class SheetError(ValueError):
	pass


def _unescape(s: str) -> str:
	return _ESC.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def find(text: str, kind: str) -> list[str]:
	"""Phrases marked for translation in a file's text; kind is "js", "html" or "py"."""
	pattern = _JS if kind == "js" else _PY
	out = []
	for m in pattern.finditer(text):
		s = _unescape(m.group("s"))
		if s.strip() and s not in out:
			out.append(s)
	return out


def places_match(source: str, translated: str) -> bool:
	"""A translation keeps every {0}, {1}… of its phrase (in any order), and adds none."""
	return sorted(PLACES.findall(source)) == sorted(PLACES.findall(translated))


def to_csv(rows: list[dict], languages: list[str]) -> str:
	"""The spreadsheet: phrase, where it is used, then a column per language."""
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(["phrase", "where", *languages])
	for row in rows:
		w.writerow(
			[row["source"], row.get("where", ""), *[(row.get("t") or {}).get(lang, "") for lang in languages]]
		)
	return buf.getvalue()


def from_csv(text: str) -> tuple[list[str], list[tuple[str, str, str]]]:
	"""A filled-in spreadsheet → (languages, [(language, phrase, translation)…]). Empty cells are
	left out; the `where` column and unknown columns without a language code are ignored."""
	text = text.lstrip("﻿")
	reader = csv.reader(io.StringIO(text))
	try:
		head = [h.strip() for h in next(reader)]
	except StopIteration:
		raise SheetError("The spreadsheet is empty") from None
	if not head or head[0].lower() not in ("phrase", "source", "source_text"):
		raise SheetError("The first column must be `phrase` (download the spreadsheet to see the layout)")
	languages = [h for h in head[1:] if h and h.lower() != "where"]
	cells = []
	for row in reader:
		if not row or not row[0].strip():
			continue
		source = row[0]
		for n, lang in enumerate(head[1:], 1):
			if lang in languages and n < len(row) and row[n].strip():
				cells.append((lang, source, row[n].strip()))
	return languages, cells
