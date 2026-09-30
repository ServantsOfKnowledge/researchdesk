"""Install / migrate hooks: roles, default settings, a sample ingest profile, desk workspace."""

import frappe

ROLES = {
	"ResDesk Manager": "Configures the portal, runs ingests, manages the catalogue.",
	"ResDesk Cataloguer": "Edits catalogue records.",
	"ResDesk Reader": "Logged-in reader: can find and read members-only books on the portal.",
}
# roles that work in the Desk; readers only use the portal
DESK_ROLES = ("ResDesk Manager", "ResDesk Cataloguer")

SAMPLE_PROFILES = [
	{
		"profile_name": "SoK Kannada sample",
		"scope_type": "Collection",
		"ia_collection": "ServantsOfKnowledge",
		"extra_filter": "language:(kan OR Kannada OR Kan)",
		"max_items": 50,
		"fetch_fulltext": 1,
		"notes": "A small starter set: 50 Kannada books from Servants of Knowledge. Edit freely.",
	},
	{
		"profile_name": "SoK English sample",
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
	apply_default_settings()
	create_sample_profiles()
	create_workspace()
	set_website_home()
	frappe.db.commit()


def set_website_home():
	"""Visitors landing on / see the library; staff still go to the Desk after login."""
	ws = frappe.get_single("Website Settings")
	if not ws.home_page:
		ws.home_page = "library"
		ws.app_name = frappe.conf.get("resdesk_portal_title") or "SoK Research Desk"
		ws.top_bar_items = []
		ws.append("top_bar_items", {"label": "Library", "url": "/library"})
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


def after_migrate():
	create_roles()
	try:
		from sok_resdesk.resdesk.doctype.rd_settings.rd_settings import apply_branding

		apply_branding()
	except Exception:
		frappe.log_error("Research Desk: could not apply branding")
	create_workspace()
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
		home = "/app/research-desk" if desk else "/library"
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
	s.portal_title = conf.get("resdesk_portal_title") or s.portal_title or "SoK Research Desk"
	s.meili_url = conf.get("resdesk_meili_url") or s.meili_url or "http://127.0.0.1:7700"
	if conf.get("resdesk_meili_key"):
		s.meili_api_key = conf.get("resdesk_meili_key")
	s.index_prefix = s.index_prefix or "rd"
	s.repository_id = conf.get("resdesk_repository_id") or s.repository_id or frappe.local.site
	s.ia_contact = conf.get("resdesk_contact") or s.ia_contact
	s.admin_email = (
		conf.get("resdesk_contact") if "@" in (conf.get("resdesk_contact") or "") else s.admin_email
	)
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
				{"label": "Open Portal", "type": "URL", "url": "/library", "color": "Orange"},
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
