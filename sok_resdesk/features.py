"""Features and institution profiles (Settings → Features).

Not every library uses everything. Each major feature can be switched off; switched off it is
**not collected**: its scheduled work stops, its Desk screens go, and nothing new of its kind is
made (the calls that would make it say so). What already exists stays, and who sees it is still
decided by access (roles and each book's visibility), never by these switches.

Profiles describe the institution. They combine: a library can be a public research portal *and*
an archive keeping its own copies. Ticking profiles switches on the union of their features and
the larger of their resource presets; each feature can still be changed by hand afterwards.

When data arrives that a switched-off feature would handle (scans with no text while OCR is off,
members-only books while reader accounts are off…), :func:`suggestions` says so, with the
numbers, on Settings → Features and the Research Desk workspace. Switching on stays the admin's
decision.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

import frappe
from frappe import _


@dataclass(frozen=True)
class Feature:
	key: str
	label: str
	what: str
	saves: str
	# Desk screens that belong to it (workspace links and shortcuts are hidden when it is off)
	doctypes: tuple[str, ...] = ()
	pages: tuple[str, ...] = ()
	# ingest sources it covers (RD Ingest Profile → Source)
	sources: tuple[str, ...] = ()


FEATURES: dict[str, Feature] = {
	f.key: f
	for f in (
		Feature(
			"page_search",
			"Page-level full-text search",
			"search inside the text of every page, page hits, search inside a book",
			"most of the search engine's disk, memory and CPU",
		),
		Feature(
			"ocr",
			"OCR",
			"reading scans with OCR, re-OCR of pages and books",
			"CPU (OCR is the heaviest work Research Desk does)",
		),
		Feature(
			"proofreading",
			"Proofreading and ground truth",
			"correcting and validating page text, sharing corrected pages as OCR ground truth",
			"worker time and a portal section",
			doctypes=("RD Page Text", "RD Ground Truth"),
		),
		Feature(
			"notes",
			"Readers' notes",
			"highlights, comments, tags and OCR error reports; research groups",
			"review work for managers",
			doctypes=("RD Annotation", "RD Research Group"),
		),
		Feature(
			"authorities",
			"Authority control",
			"authors and subjects matched to Wikidata, VIAF and LCSH, and giving back to them",
			"nightly jobs and calls to outside services",
			pages=("resdesk-authorities",),
		),
		Feature(
			"review",
			"Review queue",
			"records checked for what needs a cataloguer (no year, wrong language, duplicates)",
			"nightly checks",
			doctypes=("RD Review Flag",),
			pages=("resdesk-review",),
		),
		Feature(
			"preservation",
			"Preservation",
			"the library's own checked copies (OCFL), fixity, a second copy, BagIt exports",
			"disk (often as much as the collection itself) and nightly audits",
			doctypes=("RD Preservation Event",),
		),
		Feature(
			"identifiers",
			"Permanent identifiers",
			"ARKs for books and pages, DOIs from DataCite, tombstones",
			"little; its screens and the DataCite calls",
			doctypes=("RD Tombstone",),
		),
		Feature(
			"folders",
			"Books from folders and servers",
			"IA-style book folders, loose PDFs and Calibre libraries on disk, a NAS or a web server",
			"the folder scans",
			sources=("Folder or Server",),
		),
		Feature(
			"repositories",
			"Books from repositories",
			"DSpace, EPrints and any OAI-PMH repository, and books transcribed on Wikisource",
			"the harvests",
			sources=("Repository (OAI-PMH)", "Wikisource"),
		),
		Feature(
			"library_systems",
			"Library systems",
			"a Koha or other library catalogue matched to the books here, links sent back",
			"the imports and matching",
			doctypes=("RD Library System", "RD Library Record"),
		),
		Feature(
			"manuscripts",
			"Manuscripts and palm leaves",
			"describing manuscripts, labelling their leaves, folders of leaf photographs, the transcription list",
			"the manuscript pages and their transcription list",
		),
		Feature(
			"photographs",
			"Photographs",
			"photographs as items: EXIF, who and where, a SHA-256 of the original, a zoom viewer",
			"the photograph pages",
		),
		Feature(
			"media",
			"Audio and video",
			"recordings with a player and a time-coded transcript, in folders and from archive.org",
			"the player pages and the recordings' transcripts",
		),
		Feature(
			"deposit",
			"Repository deposit",
			"people deposit their own work (files, licence, embargo) for a reviewer to accept",
			"the deposit pages and the review screen",
			doctypes=("RD Deposit",),
		),
		Feature(
			"sharing",
			"Sharing metadata",
			"the OAI-PMH provider, IIIF manifests, pushes to Koha, Wikidata, archive.org and webhooks",
			"the push jobs, the OAI-PMH endpoint and the IIIF addresses",
			doctypes=("RD Push Target", "RD Push Run", "RD External Record"),
		),
		Feature(
			"reader_accounts",
			"Reader accounts",
			"readers signing up, sign-up requests, members-only reading",
			"the sign-up pages",
			doctypes=("RD Reader Request",),
		),
		Feature(
			"statistics",
			"Usage statistics",
			"how readers use the portal (built-in, PostHog, Plausible or Umami)",
			"the page-view log",
		),
	)
}

PRESETS = ("light", "standard", "server")  # Settings → Server → Resource Preset, smallest first


@dataclass(frozen=True)
class Profile:
	key: str
	label: str
	features: frozenset[str]
	preset: str
	languages: str = "all"  # Tesseract models it needs (OCR_LANGS); the installer asks


PROFILES: dict[str, Profile] = {
	p.key: p
	for p in (
		Profile(
			"small",
			"Small library or school",
			frozenset({"ocr", "folders", "manuscripts", "photographs"}),
			"light",
		),
		Profile(
			"portal",
			"Public research portal",
			frozenset(
				{
					"page_search",
					"ocr",
					"proofreading",
					"notes",
					"authorities",
					"review",
					"identifiers",
					"sharing",
					"statistics",
					"media",
					"manuscripts",
					"photographs",
				}
			),
			"standard",
		),
		Profile(
			"members",
			"Members-only institution",
			frozenset(
				{
					"page_search",
					"reader_accounts",
					"library_systems",
					"review",
					"sharing",
					"manuscripts",
					"photographs",
				}
			),
			"standard",
		),
		Profile(
			"archive",
			"Archive keeping its own copies",
			frozenset(
				{
					"preservation",
					"identifiers",
					"folders",
					"review",
					"media",
					"manuscripts",
					"photographs",
				}
			),
			"standard",
		),
		Profile(
			"repository",
			"University or repository front",
			frozenset(
				{
					"page_search",
					"ocr",
					"repositories",
					"folders",
					"identifiers",
					"sharing",
					"library_systems",
					"deposit",
					"review",
					"manuscripts",
					"photographs",
				}
			),
			"standard",
		),
		Profile(
			"manuscripts",
			"Manuscript library or archive",
			frozenset(
				{
					"page_search",
					"proofreading",
					"manuscripts",
					"photographs",
					"folders",
					"media",
					"preservation",
					"identifiers",
					"review",
					"sharing",
				}
			),
			"standard",
		),
		Profile(
			"photos",
			"Photograph archive",
			frozenset({"photographs", "folders", "preservation", "identifiers", "review", "sharing"}),
			"standard",
		),
		Profile(
			"langtech",
			"Language-technology partner",
			frozenset({"page_search", "ocr", "proofreading", "sharing"}),
			"server",
		),
	)
}


def field_of(key: str) -> str:
	return f"feature_{key}"


def on(key: str, doc=None) -> bool:
	"""Whether a feature is on (as saved, or in `doc`, the settings being saved). Unknown to the
	settings (an old site before migrate) = on."""
	if doc is not None:
		value = doc.get(field_of(key))
		return value is None or bool(int(value))
	try:
		value = frappe.db.get_single_value("RD Settings", field_of(key), cache=True)
	except Exception:
		return True
	return value is None or bool(int(value))


def off_message(key: str) -> str:
	return _("{0} is switched off for this library (Settings → Features).").format(_(FEATURES[key].label))


def needs(key: str):
	"""For calls that make new data of a feature: refused while it is off."""

	def wrap(fn):
		@functools.wraps(fn)
		def inner(*args, **kwargs):
			if not on(key):
				frappe.throw(off_message(key), title=_("Switched off"))
			return fn(*args, **kwargs)

		return inner

	return wrap


def scheduled(key: str):
	"""For scheduled and document-event work: skipped quietly while the feature is off."""

	def wrap(fn):
		@functools.wraps(fn)
		def inner(*args, **kwargs):
			if not on(key):
				return None
			return fn(*args, **kwargs)

		return inner

	return wrap


def for_source(source: str) -> str | None:
	return next((f.key for f in FEATURES.values() if source in f.sources), None)


def source_allowed(source: str) -> bool:
	key = for_source(source)
	return key is None or on(key)


def require_source(source: str) -> None:
	key = for_source(source)
	if key and not on(key):
		frappe.throw(off_message(key), title=_("Switched off"))


# -- profiles ----------------------------------------------------------------------------------


def from_profiles(keys) -> tuple[set[str], str]:
	"""The features and the resource preset a set of profiles adds up to (a union, the larger)."""
	chosen = [PROFILES[k] for k in keys if k in PROFILES]
	features = set().union(*(p.features for p in chosen)) if chosen else set(FEATURES)
	preset = max((p.preset for p in chosen), key=PRESETS.index, default="standard")
	return features, preset


BIG_LIBRARY = 50_000  # books: from here the server preset, whatever the profiles say


def install_choices(doc, profiles: str | None, books=None) -> None:
	"""The installer's answers (./install.sh, site_config resdesk_profiles / resdesk_books): the
	kinds of institution, ticked on the new site's settings (the save switches their features on),
	and a bigger resource preset for a big catalogue."""
	keys = [k.strip() for k in (profiles or "").replace(" ", ",").split(",") if k.strip() in PROFILES]
	for key in keys:
		doc.set(f"profile_{key}", 1)  # the save switches their features on (apply_profiles)
	try:
		books = int(books or 0)
	except (TypeError, ValueError):
		books = 0
	if books >= BIG_LIBRARY:
		doc.flags.min_preset = "server"
		if doc.meta.has_field("resource_preset"):
			doc.resource_preset = "server"


def apply_profiles(doc, force: bool = False) -> None:
	"""RD Settings.validate: ticking or unticking a profile resets the features to its set."""
	keys = [k for k in PROFILES if doc.get(f"profile_{k}")]
	if not keys or not (force or any(doc.has_value_changed(f"profile_{k}") for k in PROFILES)):
		return
	features, preset = from_profiles(keys)
	if doc.flags.get("min_preset"):
		preset = max(preset, doc.flags.min_preset, key=PRESETS.index)
	for key in FEATURES:
		doc.set(field_of(key), 1 if key in features else 0)
	if doc.meta.has_field("resource_preset"):
		doc.resource_preset = preset


# -- what a switch changes at once -------------------------------------------------------------


def changed(doc) -> bool:
	return any(doc.has_value_changed(field_of(k)) for k in FEATURES)


def apply(doc=None) -> None:
	"""After the switches change (and after every upgrade): the Desk shows only what is on."""
	frappe.clear_cache()  # the cached settings the gates read
	refresh_workspace()
	try:
		from sok_resdesk import sidebar

		sidebar.refresh()
	except Exception:
		frappe.log_error(title="Research Desk: the Desk's sidebar was not rebuilt")
	from sok_resdesk.access import apply_signup_setting
	from sok_resdesk.analytics import apply_settings as apply_analytics

	s = doc or frappe.get_single("RD Settings")
	apply_signup_setting(s)
	apply_analytics(s)
	frappe.cache.delete_value(SUGGESTIONS_KEY)


def hidden_targets() -> set[str]:
	"""The Desk screens of the features that are off."""
	out: set[str] = set()
	for f in FEATURES.values():
		if not on(f.key):
			out.update(f.doctypes)
			out.update(f.pages)
	return out


def refresh_workspace() -> None:
	"""The Research Desk workspace as it ships, less the screens of switched-off features (and any
	card left empty). Rebuilt from the shipped definition, so switching back on restores them."""
	import json
	from pathlib import Path

	if not frappe.db.exists("Workspace", "Research Desk"):
		return
	path = Path(
		frappe.get_app_path("sok_resdesk", "resdesk", "workspace", "research_desk", "research_desk.json")
	)
	shipped = json.loads(path.read_text())
	hide = hidden_targets()
	links, card = [], None
	for link in shipped.get("links", []):
		if link.get("type") == "Card Break":
			card = [dict(link)]
			links.append(card)
		elif link.get("link_to") not in hide and card is not None:
			card.append(dict(link))
	rows = [row for group in links if len(group) > 1 for row in group]
	shortcuts = [dict(s) for s in shipped.get("shortcuts", []) if s.get("link_to") not in hide]
	cards = {group[0]["label"] for group in links if len(group) > 1}
	names = {s["label"] for s in shortcuts}
	content = [
		block
		for block in json.loads(shipped.get("content") or "[]")
		if not (block.get("type") == "card" and block["data"].get("card_name") not in cards)
		and not (block.get("type") == "shortcut" and block["data"].get("shortcut_name") not in names)
	]
	ws = frappe.get_doc("Workspace", "Research Desk")
	if [(r.get("label"), r.get("link_to")) for r in rows] == [(r.label, r.link_to) for r in ws.links] and len(
		shortcuts
	) == len(ws.shortcuts):
		return
	ws.set("links", rows)
	ws.set("shortcuts", shortcuts)
	ws.content = json.dumps(content)
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.save()


def trim_boot(bootinfo) -> None:
	"""The Desk sidebar (Frappe 16 builds it apart from the workspace): the same screens go. Forms
	learn which features are off (bootinfo.resdesk_features_off), so a library without manuscripts
	does not see the manuscript fields."""
	if frappe.session.user != "Guest":
		bootinfo.resdesk_features_off = [k for k in FEATURES if not on(k)]
	hide = hidden_targets()
	if not hide:
		return
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	for key, sidebar in list(sidebars.items()):
		items = sidebar.get("items") or []
		kept = [i for i in items if i.get("link_to") not in hide]
		if len(kept) != len(items):
			sidebars[key] = {**sidebar, "items": kept}


def after_migrate() -> None:
	try:
		from sok_resdesk import sidebar

		sidebar.refresh()  # the Desk's sidebar: every screen, less switched-off features'
	except Exception:
		frappe.log_error(title="Research Desk: the Desk's sidebar was not built")
	try:
		refresh_workspace()  # the migrate synced the shipped workspace back in
	except Exception:
		frappe.log_error(title="Research Desk: the Desk's features were not applied")


# -- suggestions: data that a switched-off feature would handle ----------------------------------

SUGGESTIONS_KEY = "resdesk:feature-suggestions"


def _count(doctype: str, filters) -> int:
	try:
		return frappe.db.count(doctype, filters)
	except Exception:
		return 0


def _folders_waiting() -> int:
	import os

	try:
		from sok_resdesk.local_source import library_dir

		root = library_dir()
		return sum(
			1
			for e in os.scandir(root)
			if not e.name.startswith(".") and (e.is_dir() or e.name.lower().endswith(".pdf"))
		)
	except Exception:
		return 0


def _signals() -> dict[str, tuple[int, str]]:
	"""Per feature: how much data here it would handle, and what that is, in a sentence."""
	return {
		"ocr": (
			_count("RD Item", {"local_pdf": ("is", "set"), "has_page_text": 0}),
			_("Scanned books with no text: {0}. OCR would read them, so they can be searched."),
		),
		"page_search": (
			_count("RD Item", {"has_page_text": 1}),
			_("Books with page text: {0}. Page-level search would find words inside them."),
		),
		"proofreading": (
			_count("RD Item", {"ocr_quality": ("between", [1, 59])}),
			_("Books with poor OCR (under 60/100): {0}. Proofreading would let people correct them."),
		),
		"authorities": (
			_count("RD Creator", {"wikidata_id": ("is", "not set")}),
			_("Authors not linked to Wikidata or VIAF: {0}. Authority control would match them."),
		),
		"review": (
			_count("RD Item", {"published": 1, "year": ("in", [0, None])}),
			_("Books with no year: {0}. The review queue would list them for a cataloguer."),
		),
		"reader_accounts": (
			_count("RD Item", {"visibility": ("!=", "Public")}),
			_("Members-only books: {0}. Reader accounts would let members log in to read them."),
		),
		"preservation": (
			_count("RD Item", {"removed_from_source": 1}),
			_("Books removed from their source: {0}. Preservation would keep the library's own copies."),
		),
		"folders": (
			_folders_waiting(),
			_(
				"Book folders and PDFs waiting in the library folder: {0}. Books from folders would bring them in."
			),
		),
	}


def suggestions() -> list[dict]:
	"""Switched-off features that data here would use, with the numbers. Cached for an hour."""

	def make() -> list[dict]:
		out = []
		for key, (count, sentence) in _signals().items():
			if count and not on(key):
				out.append(
					{
						"feature": key,
						"label": _(FEATURES[key].label),
						"count": count,
						"why": sentence.format(f"{count:,}"),
					}
				)
		return out

	cached = frappe.cache.get_value(SUGGESTIONS_KEY)
	if cached is None:
		cached = make()
		frappe.cache.set_value(SUGGESTIONS_KEY, cached, expires_in_sec=3600)
	return cached


# -- whitelisted -------------------------------------------------------------------------------

MANAGERS = ("System Manager", "ResDesk Manager")


@frappe.whitelist()
def overview() -> dict:
	"""Settings → Features: every feature with its state, the profiles, and the suggestions."""
	frappe.only_for(MANAGERS)
	return {
		"features": [
			{"key": f.key, "label": _(f.label), "what": _(f.what), "saves": _(f.saves), "on": on(f.key)}
			for f in FEATURES.values()
		],
		"profiles": [
			{"key": p.key, "label": _(p.label), "features": sorted(p.features), "preset": p.preset}
			for p in PROFILES.values()
		],
		"suggestions": suggestions(),
	}


@frappe.whitelist(methods=["POST"])
def switch_on(feature: str) -> dict:
	"""A suggestion's Turn On button."""
	frappe.only_for(MANAGERS)
	if feature not in FEATURES:
		frappe.throw(_("No feature called {0}.").format(feature))
	s = frappe.get_single("RD Settings")
	s.set(field_of(feature), 1)
	s.save()
	return overview()
