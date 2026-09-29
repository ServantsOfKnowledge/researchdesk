app_name = "sok_resdesk"
app_title = "Research Desk"
app_publisher = "Servants of Knowledge"
app_description = "Open research portal and digital library for Servants of Knowledge and Internet Archive collections"
app_email = "omshivaprakash@gmail.com"
app_license = "MIT"

# Public portal ---------------------------------------------------------------

website_route_rules = [
	{"from_route": "/library/item/<item_id>", "to_route": "library/item"},
]


app_include_css = []
web_include_css = ["/assets/sok_resdesk/css/resdesk.css"]

# Install / migrate -----------------------------------------------------------

after_install = "sok_resdesk.setup.after_install"
after_migrate = "sok_resdesk.setup.after_migrate"

# Keep the search index in sync with the catalogue ----------------------------

doc_events = {
	"RD Item": {
		"on_update": "sok_resdesk.search.on_item_update",
		"on_trash": "sok_resdesk.search.on_item_trash",
	},
	# portal sign-ups become readers, or wait for approval (RD Settings → Reader Accounts)
	"User": {"after_insert": "sok_resdesk.access.on_user_insert"},
}

# Scheduled ingest (profiles set to Daily / Weekly) ---------------------------

scheduler_events = {
	"hourly": ["sok_resdesk.ingest.mark_interrupted_runs", "sok_resdesk.ingest.run_scheduled_hourly"],
	"daily": ["sok_resdesk.ingest.run_scheduled_daily"],
	"weekly": ["sok_resdesk.ingest.run_scheduled_weekly"],
}
