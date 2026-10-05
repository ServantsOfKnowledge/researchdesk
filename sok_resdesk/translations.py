"""The portal in Kannada and other languages (Desk → Portal Translations).

Every phrase readers see on the portal (in its pages, its scripts, and the library's own words:
its name, tagline, About page and collections) is listed with a column for each language the
library offers (Settings → Portal → Portal Languages). Staff fill them in on the page or in a
spreadsheet; each translation is a Frappe *Translation* record, so Frappe's own translation
machinery serves it, and a library's translations override any shipped with the app.

Readers choose their language with the switch at the top of the portal (a cookie for visitors,
their account's language when logged in); browsers that ask for a language the portal offers
get it the first time.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core import phrases as core

MANAGERS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
APP = Path(__file__).resolve().parent
# the portal's own files; Desk-only modules are left out (Frappe translates the Desk itself)
SCRIPTS = (
	"a11y.js",
	"annotate.js",
	"basket.js",
	"item.js",
	"library.js",
	"proofread.js",
	"readaloud.js",
	"media.js",
	"reader.js",
	"tips.js",
	"zoom.js",
)
PYTHON = ("about.py", "portal.py", "api.py", "annotations.py", "access.py", "catalogue.py")
CACHE_KEY = "resdesk:portal-phrases"


def portal_languages() -> list[str]:
	"""The languages the portal offers besides English, as Settings lists them (kn, hi…)."""
	raw = frappe.db.get_single_value("RD Settings", "portal_languages") or ""
	out = []
	for code in raw.replace(",", "\n").split():
		code = code.strip()
		if code and code != "en" and code not in out:
			out.append(code)
	return out


def validate_settings(doc) -> None:
	"""RD Settings.validate: every portal language is one Frappe knows; switch them on."""
	raw = doc.get("portal_languages") or ""
	codes = [c.strip() for c in raw.replace(",", "\n").split() if c.strip() and c.strip() != "en"]
	unknown = [c for c in codes if not frappe.db.exists("Language", c)]
	if unknown:
		frappe.throw(
			_(
				"Not a language code Frappe knows: {0}. Use codes such as kn, hi, ta, te, ml, mr, bn, gu, sa."
			).format(", ".join(unknown))
		)
	for c in codes:
		if not cint(frappe.db.get_value("Language", c, "enabled")):
			frappe.db.set_value("Language", c, "enabled", 1)
	doc.portal_languages = "\n".join(dict.fromkeys(codes))
	frappe.cache.delete_value("languages_with_name")
	frappe.client_cache.delete_value("languages")


# ---- the phrases -------------------------------------------------------------------------------


def _file_phrases() -> list[tuple[str, str]]:
	"""(phrase, where) for every phrase marked in the portal's files, in file order."""
	found: list[tuple[str, str]] = []
	files = [
		*sorted((APP / "www").rglob("*.html")),
		*sorted((APP / "templates" / "includes").glob("*.html")),
		*sorted((APP / "www").rglob("*.py")),
		*[APP / name for name in PYTHON],
		*[APP / "public" / "js" / name for name in SCRIPTS],
	]
	for path in files:
		if not path.exists():
			continue
		kind = path.suffix.lstrip(".")
		for s in core.find(path.read_text(encoding="utf-8"), kind):
			found.append((s, str(path.relative_to(APP))))
	return found


def _content_phrases() -> list[tuple[str, str]]:
	"""The library's own words: its name, tagline, About page, and collections."""
	out: list[tuple[str, str]] = []
	s = frappe.db.get_singles_dict("RD Settings")
	for field in ("portal_title", "portal_tagline"):
		if s.get(field):
			out.append((s[field].strip(), _("Settings")))
	about = frappe.get_cached_doc("RD About Page")
	for field in (
		"nav_label",
		"page_title",
		"meta_description",
		"headline",
		"tagline",
		"intro",
		"primary_label",
		"secondary_label",
		"steps_title",
		"highlights_title",
		"body_title",
		"body",
	):
		if (about.get(field) or "").strip():
			out.append((about.get(field).strip(), _("About page")))
	for row in [*about.steps, *about.highlights]:
		for field in ("title", "text", "link_label"):
			if (row.get(field) or "").strip():
				out.append((row.get(field).strip(), _("About page")))
	for c in frappe.get_all(
		"RD Collection",
		filters={"published": 1},
		fields=["name", "title", "description"],
		order_by="sort_order asc, title asc",
	):
		where = _("Collection {0}").format(c.name)
		if (c.title or "").strip():
			out.append((c.title.strip(), where))
		if (c.description or "").strip():
			out.append((c.description.strip(), where))
	return out


def phrases(content: bool = True) -> list[dict]:
	"""Every portal phrase once: {source, where, script} (script: used by the portal's scripts,
	so sent to the browser)."""
	files = frappe.cache.get_value(CACHE_KEY)
	if files is None:
		files = _file_phrases()
		frappe.cache.set_value(CACHE_KEY, files, expires_in_sec=3600)
	merged: dict[str, dict] = {}
	for source, where in [*files, *(_content_phrases() if content else [])]:
		row = merged.setdefault(source, {"source": source, "where": [], "script": False})
		if where not in row["where"]:
			row["where"].append(where)
		if where.endswith(".js"):
			row["script"] = True
	for row in merged.values():
		row["where"] = ", ".join(row["where"])
	return list(merged.values())


def tr(text: str | None) -> str:
	"""The library's own words (a collection's title, the tagline) in the reader's language."""
	if not text or (getattr(frappe.local, "lang", "en") or "en") == "en":
		return text or ""
	return _(text.strip())


# ---- on the portal -----------------------------------------------------------------------------


def script_messages(lang: str) -> dict:
	"""The translations the portal's scripts need, in one language."""
	if not lang or lang == "en":
		return {}
	from frappe.translate import get_all_translations

	every = get_all_translations(lang)
	return {
		p["source"]: every[p["source"]]
		for p in phrases(content=False)
		if p["script"] and p["source"] in every
	}


def website_context(context) -> dict | None:
	"""Portal pages: the scripts' translations and the language switch, in the page's head."""
	request = getattr(frappe.local, "request", None)
	path = (
		context.get("path") or getattr(frappe.local, "path", None) or (request.path if request else "") or ""
	).strip("/")
	if not (path in ("", "about", "library") or path.startswith("library/")):
		return None
	try:
		langs = portal_languages()
	except Exception:
		return None
	lang = getattr(frappe.local, "lang", "en") or "en"
	data = {"lang": lang, "messages": script_messages(lang) if lang in langs else {}}
	if langs:
		names = dict(
			frappe.get_all(
				"Language", filters={"name": ("in", langs)}, fields=["name", "language_name"], as_list=True
			)
		)
		data["languages"] = [{"code": "en", "name": "English"}] + [
			{"code": c, "name": names.get(c) or c} for c in langs
		]
	payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
	script = f"<script>window.RD_I18N = {payload};</script>" + READING_SETTINGS
	return {"head_include": (context.get("head_include") or "") + script}


# the reader's reading settings (a11y.js), set before the page is drawn so it doesn't jump
READING_SETTINGS = (
	"<script>try{var p=JSON.parse(localStorage.getItem('rd-reading')||'{}');for(var k in p)"
	"if(/^(size|leading|spacing|colours)$/.test(k)&&/^[a-z]+$/.test(p[k]))"
	"document.documentElement.setAttribute('data-rd-'+k,p[k]);}catch(e){}</script>"
)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_language(lang: str) -> dict:
	"""The portal's language switch: a cookie, for the portal only. The account's own language
	(what the Desk is shown in) is never changed by it: staff who looked at the portal in
	Kannada kept getting a half-Kannada Desk (before 0.40)."""
	if lang != "en" and lang not in portal_languages():
		frappe.throw(_("This portal is not offered in that language."))
	frappe.local.cookie_manager.set_cookie("preferred_language", lang)
	return {"lang": lang}


# the Desk and its calls keep the account's language; everything else is the portal
DESK_PATHS = ("/app", "/desk", "/assets", "/files", "/private", "/socket.io", "/login", "/update-password")


def portal_language() -> None:
	"""before_request: a logged-in reader's portal pages (and the portal's own calls) in the
	language they chose with the switch. Frappe itself goes by the account's language for anyone
	logged in, which is right for the Desk and nothing else."""
	if frappe.session.user == "Guest" or not getattr(frappe, "request", None):
		return  # visitors: Frappe reads the cookie itself
	if frappe.form_dict.get("_lang"):
		return  # a page asked for in a language (?_lang=kn, the hreflang links) gets it
	lang = frappe.request.cookies.get("preferred_language") or ""
	if not lang:
		return
	path = frappe.request.path or "/"
	if path.startswith(DESK_PATHS):
		return
	if path.startswith("/api/"):
		# a call from a Desk page keeps the account's language; one from the portal follows the switch
		referer = frappe.request.headers.get("Referer") or ""
		if "/app" in referer or "/desk" in referer or not referer:
			return
	if lang == "en" or lang in portal_languages():
		frappe.local.lang = lang


# ---- the Desk page ------------------------------------------------------------------------------


def _translations(lang: str) -> dict:
	"""What a phrase reads as in one language now, and which of those the library wrote."""
	from frappe.translate import get_translations_from_apps

	shipped = get_translations_from_apps(lang)
	own = {
		t.source_text: t.translated_text
		for t in frappe.get_all(
			"Translation",
			filters={"language": lang, "context": ("in", ("", None))},
			fields=["source_text", "translated_text"],
		)
	}
	return {"shipped": shipped, "own": own}


@frappe.whitelist()
def overview() -> dict:
	"""Desk → Portal Translations: every phrase, with what it reads as in each portal language."""
	frappe.only_for(MANAGERS)
	langs = portal_languages()
	names = dict(
		frappe.get_all(
			"Language",
			filters={"name": ("in", langs or [""])},
			fields=["name", "language_name"],
			as_list=True,
		)
	)
	tables = {lang: _translations(lang) for lang in langs}
	rows = []
	for p in phrases():
		t, own = {}, {}
		for lang in langs:
			mine = tables[lang]["own"].get(p["source"])
			t[lang] = mine if mine is not None else tables[lang]["shipped"].get(p["source"], "")
			own[lang] = mine is not None
		rows.append({**p, "t": t, "own": own})
	missing = {lang: sum(1 for r in rows if not r["t"][lang]) for lang in langs}
	return {
		"languages": [{"code": c, "name": names.get(c) or c} for c in langs],
		"rows": rows,
		"missing": missing,
	}


def _save(lang: str, source: str, text: str) -> str:
	"""Create, change or (with no text) remove the library's translation of a phrase."""
	source = source.strip()
	text = (text or "").strip()
	name = frappe.db.get_value(
		"Translation", {"language": lang, "source_text": source, "context": ("in", ("", None))}
	)
	if not text:
		if name:
			frappe.delete_doc("Translation", name, ignore_permissions=True)
			return "removed"
		return "unchanged"
	if not core.places_match(source, text):
		raise frappe.ValidationError(
			_("Keep every {{0}}, {{1}}… of the phrase in the translation: {0}").format(source[:80])
		)
	if name:
		doc = frappe.get_doc("Translation", name)
		if doc.translated_text == text:
			return "unchanged"
		doc.translated_text = text
		doc.save(ignore_permissions=True)
		return "changed"
	frappe.get_doc(
		{"doctype": "Translation", "language": lang, "source_text": source, "translated_text": text}
	).insert(ignore_permissions=True)
	return "added"


@frappe.whitelist(methods=["POST"])
def save(lang: str, source: str, text: str = "") -> dict:
	frappe.only_for(MANAGERS)
	if lang not in portal_languages():
		frappe.throw(_("Add {0} to Settings → Portal → Portal Languages first.").format(lang))
	try:
		return {"result": _save(lang, source, text)}
	except frappe.ValidationError as e:
		frappe.throw(str(e))


@frappe.whitelist()
def download() -> None:
	"""The spreadsheet of every phrase and its translations (CSV, opens in any spreadsheet)."""
	frappe.only_for(MANAGERS)
	data = overview()
	langs = [lang["code"] for lang in data["languages"]]
	frappe.response["type"] = "download"
	frappe.response["filename"] = "portal-translations.csv"
	frappe.response["filecontent"] = "﻿" + core.to_csv(data["rows"], langs)
	frappe.response["content_type"] = "text/csv; charset=utf-8"


@frappe.whitelist(methods=["POST"])
def upload(content: str) -> dict:
	"""A filled-in spreadsheet back: each non-empty cell becomes (or changes) a translation.
	Empty cells change nothing (remove a translation on the page)."""
	frappe.only_for(MANAGERS)
	try:
		langs, cells = core.from_csv(content or "")
	except core.SheetError as e:
		frappe.throw(str(e))
	offered = set(portal_languages())
	counts = {"added": 0, "changed": 0, "unchanged": 0, "skipped": 0}
	problems = []
	for lang, source, text in cells:
		if lang not in offered:
			counts["skipped"] += 1
			continue
		try:
			result = _save(lang, source, text)
			counts[result if result in counts else "unchanged"] += 1
		except frappe.ValidationError as e:
			counts["skipped"] += 1
			problems.append(str(e))
	not_offered = [lang for lang in langs if lang not in offered]
	return {**counts, "problems": problems[:20], "not_offered": not_offered}


def clear_phrase_cache() -> None:
	frappe.cache.delete_value(CACHE_KEY)
