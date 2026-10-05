"""Install / migrate hooks: roles, default settings, a sample ingest profile, desk workspace."""

import frappe
from frappe import _

ROLES = {
	"ResDesk Manager": "Configures the portal, runs ingests, manages the catalogue.",
	"ResDesk Cataloguer": "Edits catalogue records.",
	"ResDesk Reader": "Logged-in reader: can find and read members-only books on the portal.",
	"ResDesk Depositor": "Deposits their own work on the portal (Deposit), for the library to review.",
	"ResDesk Proofreader": "Corrects the page text of books on the portal (Page & text → Proofread), and runs OCR on parts of a page.",
}
# roles that work in the Desk; readers only use the portal
DESK_ROLES = ("ResDesk Manager", "ResDesk Cataloguer")

SAMPLE_PROFILES = [
	{
		"profile_name": "SOK Kannada sample",
		"scope_type": "Collection",
		"ia_collection": "ServantsOfKnowledge",
		"extra_filter": "language:(kan OR Kannada OR Kan)",
		"max_items": 50,
		"fetch_fulltext": 1,
		"notes": "A small starter set: 50 Kannada books from Servants of Knowledge. Edit freely.",
	},
	{
		"profile_name": "SOK English sample",
		"scope_type": "Collection",
		"ia_collection": "ServantsOfKnowledge",
		"extra_filter": "language:(eng OR English)",
		"max_items": 50,
		"fetch_fulltext": 1,
		"notes": "50 English-language books from Servants of Knowledge.",
	},
	{
		"profile_name": "Library folder",
		"source": "Folder or Server",
		"location": "/library-source",
		"check_archive_org": 1,
		"max_items": 0,
		"fetch_fulltext": 1,
		"notes": "Every IA-style item folder under LIBRARY_DIR (set in .env). Set Schedule to Hourly to pick up "
		"books copied in later; changed items are re-ingested automatically.",
	},
]


def after_install():
	create_roles()
	allow_large_uploads()
	apply_default_settings()
	create_sample_profiles()
	create_workspace()
	set_website_home()
	set_up_about_page()
	frappe.db.commit()


def set_up_about_page():
	"""Starting content for /about and its link in the top bar (once; edited in the Desk after)."""
	try:
		from sok_resdesk import about

		about.ensure_defaults()
		about.sync_top_bar(frappe.get_single("RD About Page"))
		from frappe.website.utils import clear_cache

		clear_cache()  # the top bar is cached with the pages
	except Exception:
		frappe.log_error("Research Desk: could not set up the About page")


def set_website_home():
	"""Visitors landing on / see the library; staff still go to the Desk after login."""
	ws = frappe.get_single("Website Settings")
	if not ws.home_page:
		ws.home_page = "library"
		ws.app_name = frappe.conf.get("resdesk_portal_title") or "SOK Research Desk"
		ws.top_bar_items = []
		ws.append("top_bar_items", {"label": "Library", "url": "/"})
		ws.save(ignore_permissions=True)
	add_help_to_top_bar()


def add_help_to_top_bar():
	"""A Help link next to Library in the portal's top bar (once; staff can remove it)."""
	if frappe.db.get_default("resdesk_help_link_added"):
		return
	ws = frappe.get_single("Website Settings")
	if not any((i.url or "").startswith("/library/help") for i in ws.top_bar_items):
		ws.append("top_bar_items", {"label": "Help", "url": "/library/help"})
		ws.save(ignore_permissions=True)
	frappe.db.set_default("resdesk_help_link_added", "1")


UPLOAD_MB = 100  # metadata files and spreadsheets for ingest and imports can be large


MAX_UPLOAD_MB = 1000  # the web proxies let requests this big through (compose.yaml, docker/proxy)


def allow_large_uploads() -> None:
	"""Uploads up to Settings → Largest Upload (default UPLOAD_MB), as System Settings → Max File
	Size, which Frappe checks; the web proxies in front let up to MAX_UPLOAD_MB through."""
	from frappe.utils import cint

	wanted = cint(frappe.db.get_single_value("RD Settings", "max_upload_mb")) or UPLOAD_MB
	if cint(frappe.db.get_single_value("System Settings", "max_file_size")) != wanted:
		frappe.db.set_single_value("System Settings", "max_file_size", wanted)


def validate_machine(doc) -> None:
	"""RD Settings.validate: workers and the upload limit within what the machine allows."""
	from frappe.utils import cint

	from sok_resdesk.server import MAX_WORKERS

	if doc.get("queue_workers") and not 1 <= cint(doc.queue_workers) <= MAX_WORKERS:
		frappe.throw(_("Parallel Workers: choose 1 to {0}.").format(MAX_WORKERS))
	if doc.get("max_upload_mb") and not 1 <= cint(doc.max_upload_mb) <= MAX_UPLOAD_MB:
		frappe.throw(_("Largest Upload: choose 1 to {0} MB.").format(MAX_UPLOAD_MB))


def apply_machine(doc) -> None:
	"""RD Settings.on_update: the upload limit at once; a new number of workers through the
	updater helper (or the command to run, when there is no helper)."""
	from frappe.utils import cint

	allow_large_uploads()
	before = doc.get_doc_before_save()
	workers = cint(doc.get("queue_workers"))
	if not workers or (before and cint(before.get("queue_workers")) == workers):
		return
	from sok_resdesk import server

	command = f"./resdesk.sh resources set QUEUE_WORKERS={workers}"
	try:
		if server.helper_configured() and server.helper_connected():
			server.request_task("apply_resources", {"workers": workers})
			frappe.msgprint(
				_("Setting {0} parallel workers on the server: Server → Tasks shows when it is done.").format(
					workers
				),
				indicator="green",
			)
			return
	except Exception as e:  # not allowed (only administrators restart parts), or Desk control off
		frappe.clear_last_message()
		reason = str(e)
	else:
		reason = _("the updater helper isn't running")
	frappe.msgprint(
		_("{0} parallel workers saved. To put it into effect, run on the server: {1} ({2})").format(
			workers, f"<code>{command}</code>", reason
		),
		indicator="orange",
	)


def after_migrate():
	create_roles()
	try:
		allow_large_uploads()
	except Exception:
		frappe.log_error("Research Desk: could not raise the upload size limit")
	try:
		from sok_resdesk.resdesk.doctype.rd_settings.rd_settings import apply_branding

		apply_branding()
	except Exception:
		frappe.log_error("Research Desk: could not apply branding")
	create_workspace()
	from sok_resdesk import deskscope

	deskscope.after_migrate()  # after the workspace: new modules are hidden too
	from sok_resdesk import features

	features.after_migrate()  # the shipped workspace, less switched-off features' screens
	try:
		from sok_resdesk.translations import clear_phrase_cache

		clear_phrase_cache()  # the portal's phrases may have changed with the code
	except Exception:
		pass
	try:
		add_help_to_top_bar()
	except Exception:
		frappe.log_error("Research Desk: could not add the Help link to the top bar")
	try:
		from sok_resdesk import guide

		guide.sync()  # form tours and the getting-started checklist
	except Exception:
		frappe.log_error("Research Desk: could not set up the on-screen guide")
	try:
		# portal collections for archive.org profiles, straight after an upgrade (in the background:
		# it may ask archive.org for the collections' names)
		frappe.enqueue("sok_resdesk.ia_sync.refresh_mirrors", queue="long", enqueue_after_commit=True)
	except Exception:
		frappe.log_error("Research Desk: could not queue the portal collections update")
	try:
		from sok_resdesk.search import MeiliClient

		MeiliClient.from_settings().setup()
	except Exception:
		# Search engine may not be up yet during migrate; the ingest job sets indexes up too.
		pass
	try:
		# last: lets the next start-up skip migrate while the code stays the same (core/schema.py)
		from sok_resdesk.core import schema

		schema.record()
	except Exception:
		frappe.log_error("Research Desk: could not record the migrated code version")


def create_roles():
	# DocType sync may already have created these roles (they appear in DocPerms),
	# so fill in missing properties rather than only creating.
	for role, desc in ROLES.items():
		desk = 1 if role in DESK_ROLES else 0
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": desk}).insert(
				ignore_permissions=True
			)
		doc = frappe.get_doc("Role", role)
		changed = False
		# staff land in the Desk after login, readers in the library
		home = "/app/research-desk" if desk else "/library"  # /library leads to / (the library)
		for field, value in (("home_page", home), ("description", desc), ("desk_access", desk)):
			current = doc.get(field)
			if doc.meta.has_field(field) and (
				int(current or 0) != value if field == "desk_access" else not current
			):
				doc.set(field, value)
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
	# Administrator should be able to run everything from day one
	admin = frappe.get_doc("User", "Administrator")
	missing = [r for r in DESK_ROLES if r not in {x.role for x in admin.roles}]
	if missing:
		admin.add_roles(*missing)


def apply_default_settings():
	"""Pick up values the installer wrote into site_config (resdesk_*)."""
	s = frappe.get_single("RD Settings")
	conf = frappe.conf
	s.portal_title = conf.get("resdesk_portal_title") or s.portal_title or "SOK Research Desk"
	s.meili_url = conf.get("resdesk_meili_url") or s.meili_url or "http://127.0.0.1:7700"
	if conf.get("resdesk_meili_key"):
		s.meili_api_key = conf.get("resdesk_meili_key")
	s.index_prefix = s.index_prefix or "rd"
	s.repository_id = conf.get("resdesk_repository_id") or s.repository_id or frappe.local.site
	s.ia_contact = conf.get("resdesk_contact") or s.ia_contact
	s.admin_email = (
		conf.get("resdesk_contact") if "@" in (conf.get("resdesk_contact") or "") else s.admin_email
	)
	from sok_resdesk import features

	features.install_choices(s, conf.get("resdesk_profiles"), conf.get("resdesk_books"))
	s.flags.ignore_mandatory = True
	s.save(ignore_permissions=True)


def create_sample_profiles():
	for p in SAMPLE_PROFILES:
		if not frappe.db.exists("RD Ingest Profile", p["profile_name"]):
			frappe.get_doc({"doctype": "RD Ingest Profile", **p}).insert(ignore_permissions=True)


def create_workspace():
	if frappe.db.exists("Workspace", "Research Desk"):
		return
	links = [
		("Card Break", "Catalogue", None),
		("Link", "Items", "RD Item"),
		("Link", "Creators", "RD Creator"),
		("Link", "Subjects", "RD Subject"),
		("Card Break", "Ingest", None),
		("Link", "Ingest Profiles", "RD Ingest Profile"),
		("Link", "Ingest Runs", "RD Ingest Run"),
		("Card Break", "Setup", None),
		("Link", "Settings", "RD Settings"),
	]
	content = [
		{
			"id": "rd-h",
			"type": "header",
			"data": {"text": '<span class="h4"><b>Research Desk</b></span>', "col": 12},
		},
		{"id": "rd-s1", "type": "shortcut", "data": {"shortcut_name": "Ingest Profiles", "col": 3}},
		{"id": "rd-s2", "type": "shortcut", "data": {"shortcut_name": "Items", "col": 3}},
		{"id": "rd-s3", "type": "shortcut", "data": {"shortcut_name": "Open Portal", "col": 3}},
		{"id": "rd-s4", "type": "shortcut", "data": {"shortcut_name": "Settings", "col": 3}},
		{"id": "rd-c1", "type": "card", "data": {"card_name": "Catalogue", "col": 4}},
		{"id": "rd-c2", "type": "card", "data": {"card_name": "Ingest", "col": 4}},
		{"id": "rd-c3", "type": "card", "data": {"card_name": "Setup", "col": 4}},
	]
	ws = frappe.get_doc(
		{
			"doctype": "Workspace",
			"name": "Research Desk",
			"label": "Research Desk",
			"title": "Research Desk",
			"module": "ResDesk",
			"icon": "book",
			"public": 1,
			"sequence_id": 1,
			"content": frappe.as_json(content),
			"shortcuts": [
				{
					"label": "Ingest Profiles",
					"type": "DocType",
					"link_to": "RD Ingest Profile",
					"color": "Blue",
				},
				{"label": "Items", "type": "DocType", "link_to": "RD Item", "color": "Green"},
				{"label": "Open Portal", "type": "URL", "url": "/", "color": "Orange"},
				{"label": "Settings", "type": "DocType", "link_to": "RD Settings", "color": "Grey"},
			],
			"links": [
				{
					"type": t,
					"label": label,
					"link_type": "DocType" if dt else None,
					"link_to": dt,
					"onboard": 0,
				}
				for t, label, dt in links
			],
		}
	)
	try:
		ws.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error("Research Desk: could not create workspace")


def complete_setup_wizard(timezone: str = "Asia/Kolkata", country: str = "India", currency: str = "INR"):
	"""Finish Frappe's first-run wizard so librarians land straight in the Desk.

	Called by docker/create-site.sh and scripts/dev-setup.sh:
	  bench --site <site> execute sok_resdesk.setup.complete_setup_wizard
	"""
	if frappe.is_setup_complete():
		return "already complete"
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	result = setup_complete(
		{
			"language": "English",
			"country": country,
			"timezone": timezone,
			"currency": currency,
		}
	)
	frappe.db.commit()
	return result


def set_base_url(url: str) -> None:
	"""The portal's public address in Settings (./resdesk.sh url, create-site.sh). Only that
	field: no save hooks, and no waiting for the search engine, which may be busy indexing."""
	frappe.db.set_single_value("RD Settings", "base_url", url.rstrip("/"))
	frappe.db.commit()
	frappe.clear_cache()
