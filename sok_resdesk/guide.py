"""On-screen guidance in the Desk: step-by-step tours of the main forms and the
getting-started checklist on the Research Desk workspace.

Both are written here as data and created (or updated) on every `bench migrate`, so a
change to a screen and its tour ship together. tests/test_docs.py checks that every field a
tour points at still exists on the form.
"""

from __future__ import annotations

import frappe
from frappe import _

MODULE = "ResDesk"
ONBOARDING = "Research Desk"
MANAGERS = ("System Manager", "ResDesk Manager")

# doctype -> [(fieldname, title, description)]. Only fields that are visible on a new form.
TOURS: dict[str, list[tuple[str, str, str]]] = {
	"RD Ingest Profile": [
		(
			"profile_name",
			"Name the selection",
			"A name you'll recognise, e.g. <i>Kannada literature 1900–1950</i>.",
		),
		(
			"source",
			"Where the books are",
			"<b>Internet Archive</b> for archive.org, <b>Folder or Server</b> for "
			"IA-style item folders on this computer, a NAS or a web server, or "
			"<b>Repository (OAI-PMH)</b> for DSpace, EPrints and other repositories.",
		),
		(
			"scope_type",
			"How to choose them",
			"By <b>collection</b> (e.g. ServantsOfKnowledge), by an archive.org "
			"<b>search query</b>, or by a list of <b>identifiers</b>.",
		),
		("ia_collection", "The collection", "The archive.org collection name, as in its web address."),
		(
			"extra_filter",
			"Narrow it down",
			"Optional archive.org search terms, e.g. <code>language:kan AND "
			"year:[1900 TO 1950]</code>. <b>Check Count</b> shows how many books match.",
		),
		("max_items", "How many", "Start small (50–100) to check the result, then raise it. 0 means all."),
		("fetch_fulltext", "Full text", "Keep this on: it makes the text of every page searchable."),
		(
			"visibility",
			"Who can see these books",
			"Leave empty to use the site default, or keep this selection for logged-in readers.",
		),
		(
			"schedule",
			"Keep it up to date",
			"Daily or Weekly picks up new books automatically. Save, then press <b>Run Ingest</b> to start.",
		),
	],
	"RD Collection": [
		("title", "Name the collection", "Readers see this title. The web address is made from it."),
		("description", "Describe it", "A few lines for the collection page: what is in it and why."),
		("published", "Show it on the portal", "Untick to keep it as a staff-only working set."),
		("featured", "Feature it", "Featured collections appear as cards on the portal home page."),
		("cover_image", "Cover", "An image for the collection card."),
		(
			"rules",
			"Fill it automatically",
			"Optional rules like <i>Subject contains Vachana</i>. Press "
			"<b>Apply Rules</b> after saving; new books that match are added as they arrive.",
		),
	],
	"RD Push Target": [
		("target_name", "Name the target", "E.g. <i>Our Koha catalogue</i>."),
		(
			"target_type",
			"Where to send metadata",
			"Internet Archive, Koha, Wikidata, or any web service (webhook).",
		),
		(
			"dry_run",
			"Dry run first",
			"While this is on, runs only log what they would send. Untick when the log looks right.",
		),
		("scope", "Which books", "One collection, or everything."),
		("auto_push", "Keep it in sync", "Send a book again whenever it is edited."),
	],
	"RD Export": [
		(
			"export_format",
			"Choose a format",
			"Spreadsheet to edit and import back, MARCXML for Koha, MODS or Dublin "
			"Core for repositories, BibTeX/RIS for reference managers, or files for archive.org.",
		),
		("scope", "Which books", "Everything, a collection, a profile, a search or a filter."),
		(
			"include_unpublished",
			"Unpublished books",
			"Tick to include books hidden from the portal. Then Save: the file is made straight away.",
		),
	],
	"RD Metadata Import": [
		(
			"import_file",
			"Attach the edited spreadsheet",
			"Export a spreadsheet first, change it, and attach it "
			"here. Only the columns in the file are changed.",
		),
		(
			"create_missing",
			"New records",
			"Tick to add rows whose ID isn't in the catalogue yet. Save, then "
			"press <b>Preview Changes</b>: nothing changes until you press <b>Apply Changes</b>.",
		),
	],
	"RD Item": [
		("title", "Title", "Titles stay in their original script; add a romanised form below."),
		("alt_title", "Romanised title", "Helps searches typed in Latin letters and goes into citations."),
		("item_type", "Document type", "Book, periodical, thesis… It sets the citation type too."),
		(
			"visibility",
			"Who can see it",
			"Public, <i>Login to read</i> (anyone finds it, members read it) or "
			"<i>Login to find</i> (members only).",
		),
		("subjects", "Subjects", "Used by the Subject filter on the portal and in exports."),
		("curated_collections", "Collections", "Your own collections this book belongs to."),
		(
			"ocr_languages",
			"OCR Languages",
			"Re-OCR reads the book's languages and English. List others here, main one first: "
			"<i>kan, san, eng</i>.",
		),
		(
			"lock_metadata",
			"Keep My Edits",
			"Ticked for you when you edit: re-ingesting won't overwrite your corrections.",
		),
	],
	"RD Ground Truth": [
		("title", "Name the set", "What it holds, e.g. <i>Kannada proofread pages, October 2026</i>."),
		(
			"pages_wanted",
			"Which pages",
			"Proofread pages, or only those a second person validated: fewer, but the surest.",
		),
		(
			"public_books_only",
			"Books anyone can read",
			"Keep this ticked for a set that goes on the portal. Its licence is chosen in Settings → Ground Truth.",
		),
	],
	"RD Research Group": [
		(
			"group_name",
			"Name the group",
			"A class, a project or a reading circle, e.g. <i>Haridasa seminar 2026</i>.",
		),
		(
			"description",
			"What it is for",
			"A line or two; members see the group's name when they share a note.",
		),
		(
			"members",
			"Members",
			"Add the readers (they need an account). Members can share notes on pages with the group.",
		),
	],
	"RD Annotation": [
		("kind", "The note", "Highlight, comment, tag, question, link, or an <b>OCR error</b> report."),
		(
			"visibility",
			"Who sees it",
			"Private (its author), a research group, or Public: public notes show to everyone once approved.",
		),
		(
			"review_status",
			"Review",
			"For public notes: read it on its page (<b>Open on its Page</b>), then <b>Approve</b> or "
			"<b>Reject</b>.",
		),
		(
			"body",
			"What the reader wrote",
			"Notes stay with their words even after the page text is corrected.",
		),
	],
	"RD Page Text": [
		(
			"status",
			"Where the page stands",
			"<b>Machine</b>: a re-OCR nobody checked. <b>Proofread</b>: corrected by a person. "
			"<b>Validated</b>: checked again, unchanged, by a second person.",
		),
		(
			"is_current",
			"The current version",
			"What readers see, search finds and citations quote. Older versions stay; proofreaders bring one "
			"back with <b>Make current</b> in the portal.",
		),
		(
			"text",
			"The page's text",
			"Proofreaders edit it in the portal (Page & text → Proofread), next to the image.",
		),
		(
			"zones",
			"How it was read",
			"The parts of the page read by OCR, in reading order (columns, headings).",
		),
	],
	"RD Settings": [
		("portal_title", "Your library's name", "Shown on the portal, in the browser tab and in citations."),
		("portal_tagline", "Tagline", "One line under the name on the portal home page."),
		("portal_logo", "Logo", "Shown in the top bar and on the home page."),
		("home_banner", "Home page picture", "Optional background for the search box on the home page."),
		(
			"guest_access",
			"Visitors",
			"What people who are not logged in can do: everything each book allows, "
			"only see records, or nothing.",
		),
		(
			"reader_signup",
			"Reader accounts",
			"Staff add readers, anyone can sign up, or sign-ups wait for approval.",
		),
	],
}

# The getting-started checklist on the Research Desk workspace (a custom block; see
# public/js/desk_help.js). Frappe's own onboarding widget is not shown on v16 workspaces.
# key: (title, description, action, done-when)
STEPS = [
	(
		"brand",
		"Name your library and add a logo",
		"Your library's name, logo and tagline appear on the portal, in the Desk and in citations.",
		{"label": "Open Settings", "tour": "RD Settings", "route": ["Form", "RD Settings"]},
		"logo",
	),
	(
		"ingest",
		"Bring in your first books",
		"An ingest profile says which books to bring in: an archive.org collection or search, or your own "
		"folders. Save it and press Run Ingest.",
		{
			"label": "Make a profile",
			"tour": "RD Ingest Profile",
			"route": ["Form", "RD Ingest Profile", "new"],
		},
		"ingest_done",
	),
	(
		"jobs",
		"Watch the ingest",
		"Books arrive in batches in the background. Background Jobs shows progress; pause, resume or stop from there.",
		{"label": "Open Background Jobs", "route": ["resdesk-jobs"]},
		"visited",
	),
	(
		"access",
		"Decide who can see what",
		"Everything public, a public catalogue with reading for members, or an internal library.",
		{"label": "Open access settings", "route": ["Form", "RD Settings"], "field": "guest_access"},
		"visited",
	),
	(
		"collection",
		"Make a collection",
		"Group books your way, by hand or with rules. Each collection gets its own page on the portal.",
		{"label": "Make a collection", "tour": "RD Collection", "route": ["Form", "RD Collection", "new"]},
		"collection",
	),
	(
		"readers",
		"Readers' notes and proofreading",
		"Readers keep notes on pages and report OCR errors; proofreaders correct the text. Give volunteers "
		"the ResDesk Proofreader role, make research groups, and review public notes here.",
		{"label": "Open Annotations", "route": ["List", "RD Annotation"]},
		"visited",
	),
	(
		"guide",
		"Read the staff guide",
		"A short tour of the Desk with pictures. Every screen's Help menu opens the right section.",
		{"label": "Open Help", "route": ["resdesk-help", "staff-guide"]},
		"visited",
	),
]
BLOCK = "Research Desk Checklist"
NUMBERS_BLOCK = "Research Desk Numbers"
STATE_KEY = "resdesk_checklist"


def sync() -> None:
	"""Create or update the tours and the checklist block (called on migrate)."""
	for doctype, steps in TOURS.items():
		_sync_tour(doctype, steps)
	_sync_checklist_block()


def _sync_tour(doctype: str, steps) -> None:
	meta = frappe.get_meta(doctype)
	doc = (
		frappe.get_doc("Form Tour", doctype)
		if frappe.db.exists("Form Tour", doctype)
		else frappe.new_doc("Form Tour")
	)
	doc.update(
		{
			"title": doctype,
			"reference_doctype": doctype,
			"module": MODULE,
			"is_standard": 0,
			"view_name": "Form",
			"save_on_complete": 0,
			"first_document": 0,
			"ui_tour": 0,
		}
	)
	doc.set("steps", [])
	for fieldname, title, description in steps:
		df = meta.get_field(fieldname)
		if not df:
			continue
		doc.append(
			"steps",
			{
				"fieldname": fieldname,
				"label": df.label,
				"fieldtype": df.fieldtype,
				"title": title,
				"description": description,
				"position": "Bottom",
			},
		)
	doc.flags.ignore_permissions = True
	doc.save() if not doc.is_new() else doc.insert()


def _sync_checklist_block() -> None:
	"""The workspace blocks only hold a placeholder; desk_help.js draws the checklist and the
	numbers (dashboard.py)."""
	_sync_block(BLOCK, "rd-checklist", "rd_checklist")
	_sync_block(NUMBERS_BLOCK, "rd-numbers", "rd_numbers")


def _sync_block(name: str, css_class: str, fn: str) -> None:
	values = {
		"html": f'<div class="{css_class}"></div>',
		"script": f"window.{fn} && window.{fn}(root_element);",
		"style": "",
		"private": 0,
	}
	if frappe.db.exists("Custom HTML Block", name):
		doc = frappe.get_doc("Custom HTML Block", name)
		doc.update(values)
	else:
		doc = frappe.new_doc("Custom HTML Block")
		doc.update(values)
	doc.set("roles", [{"role": r} for r in MANAGERS])
	if doc.is_new():
		doc.insert(ignore_permissions=True, set_name=name)
	else:
		doc.save(ignore_permissions=True)

	# the block sits at the top of the Research Desk workspace (resdesk/workspace/research_desk)


def _state() -> dict:
	raw = frappe.db.get_default(STATE_KEY)
	try:
		return frappe.parse_json(raw) if raw else {}
	except Exception:
		return {}


def _save_state(state: dict) -> None:
	frappe.db.set_default(STATE_KEY, frappe.as_json(state))


def _auto_done() -> dict:
	return {
		"logo": bool(frappe.db.get_single_value("RD Settings", "portal_logo")),
		"ingest_done": bool(
			frappe.db.exists("RD Ingest Run", {"status": ("in", ["Completed", "Completed with Errors"])})
		),
		"collection": bool(frappe.db.count("RD Collection")),
	}


@frappe.whitelist()
def checklist() -> dict:
	"""The getting-started steps with what is done, for the workspace block."""
	frappe.only_for(MANAGERS)
	state, auto = _state(), _auto_done()
	steps = []
	for key, title, description, action, when in STEPS:
		done = key in state.get("done", []) or bool(auto.get(when))
		steps.append(
			{
				"key": key,
				"title": _(title),
				"description": _(description),
				"action": {**action, "label": _(action["label"])},
				"mark_on_click": when == "visited",
				"done": done,
				"skipped": key in state.get("skipped", []),
			}
		)
	finished = all(s["done"] or s["skipped"] for s in steps)
	return {"steps": steps, "hidden": bool(state.get("hidden")), "finished": finished}


@frappe.whitelist()
def checklist_mark(key: str, what: str = "done") -> dict:
	"""Record a step as done (visited) or skipped, or hide/show (`what`) the whole checklist."""
	frappe.only_for(MANAGERS)
	state = _state()
	if what == "hide":
		state["hidden"] = 1
	elif what == "show":
		state.pop("hidden", None)
	elif what in ("done", "skipped"):
		if key not in {s[0] for s in STEPS}:
			frappe.throw(_("Unknown step"))
		state[what] = sorted(set(state.get(what, [])) | {key})
	_save_state(state)
	return checklist()


def mark_visited(key: str) -> None:
	"""Called when a manager opens Background Jobs or Help, ticking those steps."""
	if not any(r in frappe.get_roles() for r in MANAGERS):
		return
	state = _state()
	if key not in state.get("done", []):
		state["done"] = sorted(set(state.get("done", [])) | {key})
		_save_state(state)


@frappe.whitelist()
def restart_checklist() -> None:
	"""Show the getting-started checklist again (Help → menu)."""
	frappe.only_for(MANAGERS)
	_save_state({})
