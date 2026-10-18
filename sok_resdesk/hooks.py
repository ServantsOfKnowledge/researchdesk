from sok_resdesk import __version__

app_name = "sok_resdesk"
app_title = "Research Desk"
app_publisher = "Servants of Knowledge"
app_description = "Open-source digital library, archive and research platform for books, manuscripts, photographs and recordings"
app_email = "omshivaprakash@gmail.com"
app_license = "MIT"
# the app's own logo (Frappe's apps screen, Desk sidebar); a library's logo from
# RD Settings replaces it on the portal and in the Desk
app_logo_url = "/assets/sok_resdesk/images/sok-logo.png"
add_to_apps_screen = [
	{
		"name": "sok_resdesk",
		"logo": "/assets/sok_resdesk/images/sok-logo.png",
		"title": "Research Desk",
		"route": "/app/research-desk",
	}
]

# Public portal ---------------------------------------------------------------

# permanent ARKs resolve on the portal itself: /ark:/<naan>/<name>[/n<leaf>] (identifiers.py)
page_renderer = ["sok_resdesk.identifiers.ArkPage"]

website_route_rules = [
	{"from_route": "/library/item/<item_id>", "to_route": "library/item"},
	{"from_route": "/library/collection/<collection>", "to_route": "library/collection"},
	{"from_route": "/library/help/<slug>", "to_route": "library/help"},
	{"from_route": "/library/ground-truth", "to_route": "library/ground_truth"},
	{"from_route": "/library/archive/<unit>", "to_route": "library/archive_unit"},
	{"from_route": "/library/entity/<entity>", "to_route": "library/entity"},
	{"from_route": "/library/tag/<tag>", "to_route": "library/tag"},
]


# the Account menu on the portal: My profile
portal_menu_items = [
	{"title": "About me", "route": "/library/profile", "reference_doctype": "", "role": ""},
]

# our Desk pages' accessibility fixes (desk.css)
app_include_css = [f"/assets/sok_resdesk/css/desk.css?v={__version__}"]
# Help and Take-the-tour buttons on Research Desk screens
app_include_js = [
	f"/assets/sok_resdesk/js/desk_help.js?v={__version__}",
	f"/assets/sok_resdesk/js/desk_only.js?v={__version__}",
]
boot_session = [
	"sok_resdesk.help.boot_session",
	"sok_resdesk.deskscope.trim_boot",
	# switched-off features' screens leave the sidebar (Settings → Features)
	"sok_resdesk.features.trim_boot",
	# only a System Manager is shown the Administration section
	"sok_resdesk.sidebar.trim_boot",
	# the library's own logo on the Desk's app icon
	"sok_resdesk.sidebar.brand_boot",
]
# ?v=: browsers keep /assets for a year (Frappe's web server), so each release gets new addresses
web_include_css = [f"/assets/sok_resdesk/css/resdesk.css?v={__version__}"]
# usage statistics on portal pages, when switched on in Settings (analytics.py)
# and accessibility helpers (a11y.js: skip link, the language of Indic text, less motion)
web_include_js = [
	f"/assets/sok_resdesk/js/analytics.js?v={__version__}",
	f"/assets/sok_resdesk/js/a11y.js?v={__version__}",
	f"/assets/sok_resdesk/js/ime.js?v={__version__}",
]
# {{ library_url() }} in portal templates: / (the site's home page), or /library
jinja = {
	"methods": [
		"sok_resdesk.portal.library_url",
		"sok_resdesk.portal.asset",
		"sok_resdesk.portal.lang_tag",
		"sok_resdesk.portal.text_lang",
	]
}
# the portal's scripts in the reader's language, and the language switch (translations.py)
update_website_context = [
	"sok_resdesk.translations.website_context",
	# canonical address, the page in each portal language, noindex for searches (seo.py)
	"sok_resdesk.seo.website_context",
]
# / shows the library to everyone, also to logged-in staff whose role has another home page
# security headers on every response (security.py)
after_request = ["sok_resdesk.security.add_headers"]
before_request = [
	# Classified mode: refuse outside web requests (classified.py)
	"sok_resdesk.classified.install_guard",
	# /iiif/…: manifests and page images for IIIF viewers (answered here, before routing)
	"sok_resdesk.iiif.before_request",
	# /opds: the library as an e-reader catalogue (OPDS 1.2)
	"sok_resdesk.opds.before_request",
	# /sru: the catalogue for older library systems and Z39.50 gateways (SRU 1.2)
	"sok_resdesk.sru.before_request",
	"sok_resdesk.portal.home_is_library",
	# portal pages in the language chosen on the portal; the Desk in the account's own
	"sok_resdesk.translations.portal_language",
]

# Install / migrate -----------------------------------------------------------

after_install = "sok_resdesk.setup.after_install"
after_migrate = ["sok_resdesk.setup.after_migrate", "sok_resdesk.classified.apply"]
before_migrate = ["sok_resdesk.classified.install_guard"]
# Classified mode in background jobs too
before_job = ["sok_resdesk.classified.install_guard"]

# Keep the search index in sync with the catalogue ----------------------------

# the audit log (Governance Mode)
on_session_creation = ["sok_resdesk.audit.on_login", "sok_resdesk.directory.on_login"]
on_logout = ["sok_resdesk.audit.on_logout"]

# Governance Mode: the Desk's lists and forms of items show only what the person is cleared for
permission_query_conditions = {
	"RD Item": "sok_resdesk.access.item_query_conditions",
	"RD Page Text": "sok_resdesk.access.page_text_conditions",
	"RD Annotation": "sok_resdesk.access.annotation_conditions",
	"RD Review Flag": "sok_resdesk.access.review_flag_conditions",
	"RD Ground Truth": "sok_resdesk.access.ground_truth_conditions",
	"RD External Record": "sok_resdesk.access.external_record_conditions",
	"RD Item Scope": "sok_resdesk.clearance.scope_conditions",
	"RD File": "sok_resdesk.clearance.file_conditions",
	"RD File Record": "sok_resdesk.clearance.file_record_conditions",
	"RD File Movement": "sok_resdesk.clearance.file_movement_conditions",
	"RD Disclosure Request": "sok_resdesk.clearance.disclosure_conditions",
	"RD Disclosure Record": "sok_resdesk.clearance.disclosure_record_conditions",
	"RD Disclosure Redaction": "sok_resdesk.clearance.disclosure_redaction_conditions",
}
# What core asks of the governance layer (sok_resdesk/seams.py); an install without it lists none of these.
resdesk_event_sinks = ["sok_resdesk.audit.sink"]
resdesk_governed = ["sok_resdesk.audit.on"]
resdesk_item_cleared = ["sok_resdesk.clearance.item_cleared"]
resdesk_item_scope = ["sok_resdesk.clearance.scope_of"]
resdesk_cleared_sql = ["sok_resdesk.clearance.cleared_sql"]
resdesk_search_clause = ["sok_resdesk.clearance.search_clause"]
resdesk_health_checks = ["sok_resdesk.classified.health", "sok_resdesk.directory.health"]

has_permission = {
	"RD Item": "sok_resdesk.access.item_has_permission",
	"RD Page Text": "sok_resdesk.access.by_item_has_permission",
	"RD Annotation": "sok_resdesk.access.by_item_has_permission",
	"RD Review Flag": "sok_resdesk.access.by_item_has_permission",
	"RD Ground Truth": "sok_resdesk.access.by_item_has_permission",
	"RD External Record": "sok_resdesk.access.by_item_has_permission",
	"RD Item Scope": "sok_resdesk.clearance.scope_has_permission",
	"RD File": "sok_resdesk.clearance.file_has_permission",
	"RD Disclosure Request": "sok_resdesk.clearance.disclosure_has_permission",
}

doc_events = {
	"RD Item": {
		"on_update": [
			"sok_resdesk.search.on_item_update",
			"sok_resdesk.outbound.on_item_change",
			# the review queue's questions answered (or asked) as soon as a person edits the book
			"sok_resdesk.review.on_item_update",
		],
		"on_trash": [
			"sok_resdesk.retention.on_item_trash",  # first: a record under a legal hold is not deleted
			"sok_resdesk.search.on_item_trash",
			"sok_resdesk.review.on_item_trash",
			"sok_resdesk.outbound.reconcile_soon",
		],
	},
	# portal sign-ups become readers, or wait for approval (RD Settings → Reader Accounts)
	"User": {
		"after_insert": ["sok_resdesk.access.on_user_insert", "sok_resdesk.notifications.quiet_new_user"],
		# staff see Research Desk, not Frappe's own workspaces (Settings → The Desk)
		"before_validate": [
			"sok_resdesk.deskscope.before_validate",
			# a super admin is also a manager, so every screen and permission a manager has is theirs
			"sok_resdesk.access.super_admin_is_manager",
		],
	},
	# directory sign-in: refused before Frappe tries the connection or saves the provider
	# (again after validation: Frappe corrects the spelling of a role only then)
	"LDAP Settings": {
		"before_validate": "sok_resdesk.directory.check_ldap",
		"validate": "sok_resdesk.directory.check_ldap",
	},
	"Social Login Key": {
		"before_validate": "sok_resdesk.directory.check_social_key",
		"validate": "sok_resdesk.directory.check_social_key",
	},
	"RD Legal Hold": {
		"validate": "sok_resdesk.retention.on_hold_validate",
		"on_update": "sok_resdesk.retention.on_hold_change",
	},
	"RD Clearance": {
		"on_update": "sok_resdesk.classification.on_clearance_change",
		"on_trash": "sok_resdesk.classification.on_clearance_change",
	},
	"RD Collection": {"on_trash": "sok_resdesk.curation.on_collection_trash"},
	# a public note's tags and Wikidata item are searched with its book
	"RD Annotation": {
		"on_update": "sok_resdesk.annotations.on_change",
		"on_trash": "sok_resdesk.annotations.on_change",
	},
	# a profile's portal collection (Keep in Step with archive.org)
	"RD Ingest Profile": {"on_update": "sok_resdesk.ia_sync.on_profile_update"},
	"RD Settings": {
		"validate": "sok_resdesk.classification.check_governance_switch",
		"on_update": ["sok_resdesk.ia_sync.on_settings_update", "sok_resdesk.identifiers.on_settings_change"],
	},
}

# Scheduled ingest (profiles set to Daily / Weekly) ---------------------------

# Email is for account messages only: Frappe's own notifications (a mention, an assignment, a share,
# energy points) stay in the Desk bell. Frappe skips "Alert" itself; this adds the rest.
notification_skip_email_types = ["Mention", "Assignment", "Share", "Energy Point"]

scheduler_events = {
	# quiet hours: pause all background work at set times (RD Settings → Machine Resources)
	"cron": {
		"*/5 * * * *": ["sok_resdesk.jobs.apply_quiet_hours"],
		# runs that lost their workers: marked Interrupted and carried on by themselves
		# + the Server page's alerts when a part stops working (RD Settings → Server & Updates).
		# One key, one list: a second "*/10 * * * *" entry would silently replace the first.
		"*/10 * * * *": [
			"sok_resdesk.ingest.mark_interrupted_runs",
			"sok_resdesk.server.watch",
			# page text that waited (Books first, Hold page text) goes when the engine has room
			"sok_resdesk.search_queue.every_ten_minutes",
			# jobs whose worker stopped are cleared and queued again (Background Jobs → Machine)
			"sok_resdesk.watchdog.run",
		],
		# automatic backups, at night (server time zone)
		"30 2 * * *": ["sok_resdesk.server.scheduled_backup"],
		# preservation copies and their fixity checks, after the backup (Settings → Preservation)
		"15 3 * * *": ["sok_resdesk.preservation.daily"],
	},
	# books that left the public are taken off the public mirror (if there is one)
	"hourly": ["sok_resdesk.ingest.run_scheduled_hourly", "sok_resdesk.outbound.reconcile_all"],
	"daily": [
		# records whose retention period has ended are listed for the records officer (Governance)
		"sok_resdesk.retention.prepare",
		# LDAP accounts the directory no longer has are switched off (Governance)
		"sok_resdesk.directory.sync",
		# deposits whose embargo has ended become readable (Settings → Features → Repository deposit)
		"sok_resdesk.deposit.release_embargoes",
		"sok_resdesk.ingest.run_scheduled_daily",
		# profiles set to Manual but kept in step with archive.org
		"sok_resdesk.ia_sync.run_daily",
		"sok_resdesk.server.scheduled_update_check",
		# books that came in without an ARK (minting failed) get one
		"sok_resdesk.identifiers.assign_missing",
		# OCR quality for books not scored yet, from the page text kept here
		"sok_resdesk.ocr.daily",
		# books whose page text was counted by OCR page rather than page shown (before 0.24.1)
		"sok_resdesk.page_order.daily",
		# DOIs for the books of collections that give them, and metadata changes sent to DataCite
		"sok_resdesk.datacite.daily",
		# authors and subjects matched to Wikidata / LCSH, when Settings → Authorities says so
		"sok_resdesk.authority.nightly",
		# records that need a cataloguer's eye (Desk → Review Queue)
		"sok_resdesk.review.nightly",
		# the search engine's record of finished tasks, kept to the last week
		"sok_resdesk.search_queue.daily",
		# scans without text still waiting to be read with OCR
		"sok_resdesk.pdfs.daily",
	],
	"weekly": [
		"sok_resdesk.ingest.run_scheduled_weekly",
		# BagIt exports older than two weeks (they can be made again)
		"sok_resdesk.preservation.clean_exports",
	],
}
