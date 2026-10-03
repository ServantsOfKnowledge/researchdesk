app_name = "sok_resdesk"
app_title = "Research Desk"
app_publisher = "Servants of Knowledge"
app_description = (
	"Open research portal and digital library for Servants of Knowledge and Internet Archive collections"
)
app_email = "omshivaprakash@gmail.com"
app_license = "MIT"
# the app's own logo (Frappe's apps screen, Desk sidebar); a library's logo from
# RD Settings replaces it on the portal and in the Desk
app_logo_url = "/assets/sok_resdesk/images/resdesk-logo.svg"
add_to_apps_screen = [
	{
		"name": "sok_resdesk",
		"logo": "/assets/sok_resdesk/images/resdesk-logo.svg",
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
	{"from_route": "/library/entity/<entity>", "to_route": "library/entity"},
	{"from_route": "/library/tag/<tag>", "to_route": "library/tag"},
]


app_include_css = []
# Help and Take-the-tour buttons on Research Desk screens
app_include_js = ["/assets/sok_resdesk/js/desk_help.js"]
boot_session = "sok_resdesk.help.boot_session"
web_include_css = ["/assets/sok_resdesk/css/resdesk.css"]
# usage statistics on portal pages, when switched on in Settings (analytics.py)
# and accessibility helpers (a11y.js: skip link, the language of Indic text, less motion)
web_include_js = ["/assets/sok_resdesk/js/analytics.js", "/assets/sok_resdesk/js/a11y.js"]
# {{ library_url() }} in portal templates: / (the site's home page), or /library
jinja = {
	"methods": [
		"sok_resdesk.portal.library_url",
		"sok_resdesk.portal.lang_tag",
		"sok_resdesk.portal.text_lang",
	]
}
# / shows the library to everyone, also to logged-in staff whose role has another home page
before_request = ["sok_resdesk.portal.home_is_library"]

# Install / migrate -----------------------------------------------------------

after_install = "sok_resdesk.setup.after_install"
after_migrate = "sok_resdesk.setup.after_migrate"

# Keep the search index in sync with the catalogue ----------------------------

doc_events = {
	"RD Item": {
		"on_update": ["sok_resdesk.search.on_item_update", "sok_resdesk.outbound.on_item_change"],
		"on_trash": "sok_resdesk.search.on_item_trash",
	},
	# portal sign-ups become readers, or wait for approval (RD Settings → Reader Accounts)
	"User": {"after_insert": "sok_resdesk.access.on_user_insert"},
	"RD Collection": {"on_trash": "sok_resdesk.curation.on_collection_trash"},
	# a public note's tags and Wikidata item are searched with its book
	"RD Annotation": {
		"on_update": "sok_resdesk.annotations.on_change",
		"on_trash": "sok_resdesk.annotations.on_change",
	},
	# a profile's portal collection (Keep in Step with archive.org)
	"RD Ingest Profile": {"on_update": "sok_resdesk.ia_sync.on_profile_update"},
	"RD Settings": {
		"on_update": ["sok_resdesk.ia_sync.on_settings_update", "sok_resdesk.identifiers.on_settings_change"]
	},
}

# Scheduled ingest (profiles set to Daily / Weekly) ---------------------------

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
		],
		# automatic backups, at night (server time zone)
		"30 2 * * *": ["sok_resdesk.server.scheduled_backup"],
		# preservation copies and their fixity checks, after the backup (Settings → Preservation)
		"15 3 * * *": ["sok_resdesk.preservation.daily"],
	},
	"hourly": ["sok_resdesk.ingest.run_scheduled_hourly"],
	"daily": [
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
	],
	"weekly": [
		"sok_resdesk.ingest.run_scheduled_weekly",
		# the search engine's record of finished tasks, kept to the last week
		"sok_resdesk.search_queue.weekly",
		# BagIt exports older than two weeks (they can be made again)
		"sok_resdesk.preservation.clean_exports",
	],
}
