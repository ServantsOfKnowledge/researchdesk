"""The portal's phrases for translation (core/phrases.py) and the scripts that use them.
Pure Python: runs in CI with plain pytest."""

import re
from pathlib import Path

import pytest

from sok_resdesk.core import phrases

APP = Path(__file__).resolve().parents[1]
SCRIPTS = APP / "public" / "js"


def _portal_scripts() -> list[str]:
	text = (APP / "translations.py").read_text(encoding="utf-8")
	block = re.search(r"SCRIPTS = \((.*?)\)", text, re.S).group(1)
	return re.findall(r'"([\w.]+\.js)"', block)


def test_finds_marked_phrases_in_each_kind_of_file():
	js = """el.textContent = __("Copied ✓"); x = __('It\\'s here'); y = __("{0} books", [n]); z = foo__("no")"""
	assert phrases.find(js, "js") == ["Copied ✓", "It's here", "{0} books"]
	html = """{{ _("Search") }} <input placeholder="{{ _('Search titles, authors…') }}"> {{ _("Search") }}"""
	assert phrases.find(html, "html") == ["Search", "Search titles, authors…"]
	py = """frappe.throw(_("Not a language code Frappe knows: {0}.").format(x)); obj._("no"); f"{_('Collections')} ·\""""
	assert phrases.find(py, "py") == ["Not a language code Frappe knows: {0}.", "Collections"]


def test_python_underscore_is_not_found_in_javascript():
	assert phrases.find('_("not a script phrase")', "js") == []


def test_places_must_be_kept():
	assert phrases.places_match("{0} books", "{0} ಪುಸ್ತಕಗಳು")
	assert phrases.places_match("Add {0} to “{1}”?", "“{1}”ಗೆ {0} ಸೇರಿಸುವುದೇ?")
	assert not phrases.places_match("{0} books", "ಪುಸ್ತಕಗಳು")
	assert not phrases.places_match("Page {0} of {1}", "ಪುಟ {0} / {0}")


def test_spreadsheet_round_trip():
	rows = [
		{"source": "Search", "where": "templates", "t": {"kn": "ಹುಡುಕಿ", "hi": ""}},
		{"source": 'Say "hi", then go', "where": "library.js", "t": {"kn": "", "hi": "नमस्ते"}},
	]
	text = phrases.to_csv(rows, ["kn", "hi"])
	assert text.splitlines()[0] == "phrase,where,kn,hi"
	langs, cells = phrases.from_csv("﻿" + text)
	assert langs == ["kn", "hi"]
	assert cells == [("kn", "Search", "ಹುಡುಕಿ"), ("hi", 'Say "hi", then go', "नमस्ते")]


def test_spreadsheet_needs_the_phrase_column():
	with pytest.raises(phrases.SheetError):
		phrases.from_csv("text,kn\nSearch,ಹುಡುಕಿ\n")
	with pytest.raises(phrases.SheetError):
		phrases.from_csv("")


def test_every_portal_script_translates_its_words():
	"""Each portal script takes __ from a11y.js (window.rdT), so a reader's language reaches it;
	and the list in translations.py covers every portal script."""
	listed = set(_portal_scripts())
	desk_only = {"desk_help.js", "analytics.js"}
	on_disk = {p.name for p in SCRIPTS.glob("*.js")} - desk_only
	assert listed == on_disk, f"translations.SCRIPTS and public/js differ: {sorted(listed ^ on_disk)}"
	for name in listed - {"a11y.js"}:
		text = (SCRIPTS / name).read_text(encoding="utf-8")
		if "__(" in text:
			assert "const __ = window.rdT" in text, f"{name} uses __ without taking it from a11y.js"


def test_no_phrase_is_built_from_pieces():
	"""__(`…${x}…`) can't be translated (each reader's phrase is different): use {0} instead."""
	for name in _portal_scripts():
		text = (SCRIPTS / name).read_text(encoding="utf-8")
		assert not re.search(r"__\(\s*`", text), f"{name}: a template string passed to __()"


def test_scripts_show_no_untranslated_messages():
	"""The usual ways a script shows words to readers carry __()."""
	shown = re.compile(r"""(textContent\s*=|confirm\(|prompt\(|alertMsg\(|say\()\s*["'`][A-Za-z]""")
	for name in _portal_scripts():
		text = (SCRIPTS / name).read_text(encoding="utf-8")
		bad = [line.strip() for line in text.splitlines() if shown.search(line)]
		assert not bad, f"{name}: wrap these in __(): {bad[:3]}"
