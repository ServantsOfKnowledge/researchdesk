app_name = "sok_resdesk_governance"
app_title = "Research Desk Governance"
app_publisher = "Servants of Knowledge"
app_description = "The records-office features of Research Desk: audit log, classification, retention, file register, directory sign-in, disclosure"
app_email = "omshivaprakash@gmail.com"
app_license = "MIT"

# Research Desk itself comes first; this app only adds to it
required_apps = ["sok_resdesk"]

# Classified mode: refuse outside requests, in web requests, background jobs and migrations
before_request = ["sok_resdesk_governance.classified.install_guard"]
before_migrate = ["sok_resdesk_governance.classified.install_guard"]
before_job = ["sok_resdesk_governance.classified.install_guard"]
after_migrate = ["sok_resdesk_governance.classified.apply"]

# the audit log, and directory sign-in
on_session_creation = ["sok_resdesk_governance.audit.on_login", "sok_resdesk_governance.directory.on_login"]
on_logout = ["sok_resdesk_governance.audit.on_logout"]

# What core asks of this app (sok_resdesk/seams.py); an install without it lists none of these.
resdesk_event_sinks = ["sok_resdesk_governance.audit.sink"]
resdesk_governed = ["sok_resdesk_governance.audit.on"]
resdesk_item_cleared = ["sok_resdesk_governance.clearance.item_cleared"]
resdesk_item_scope = ["sok_resdesk_governance.clearance.scope_of"]
resdesk_cleared_sql = ["sok_resdesk_governance.clearance.cleared_sql"]
resdesk_search_clause = ["sok_resdesk_governance.clearance.search_clause"]
resdesk_health_checks = [
	"sok_resdesk_governance.classified.health",
	"sok_resdesk_governance.directory.health",
]

# the Desk's lists and forms show only what the person is cleared for
permission_query_conditions = {
	"RD Item Scope": "sok_resdesk_governance.clearance.scope_conditions",
	"RD File": "sok_resdesk_governance.clearance.file_conditions",
	"RD File Record": "sok_resdesk_governance.clearance.file_record_conditions",
	"RD File Movement": "sok_resdesk_governance.clearance.file_movement_conditions",
	"RD Disclosure Request": "sok_resdesk_governance.clearance.disclosure_conditions",
	"RD Disclosure Record": "sok_resdesk_governance.clearance.disclosure_record_conditions",
	"RD Disclosure Redaction": "sok_resdesk_governance.clearance.disclosure_redaction_conditions",
}
has_permission = {
	"RD Item Scope": "sok_resdesk_governance.clearance.scope_has_permission",
	"RD File": "sok_resdesk_governance.clearance.file_has_permission",
	"RD Disclosure Request": "sok_resdesk_governance.clearance.disclosure_has_permission",
}

doc_events = {
	# a record under a legal hold is not deleted
	"RD Item": {"on_trash": "sok_resdesk_governance.retention.on_item_trash"},
	# directory sign-in: refused before Frappe tries the connection or saves the provider
	# (again after validation: Frappe corrects the spelling of a role only then)
	"LDAP Settings": {
		"before_validate": "sok_resdesk_governance.directory.check_ldap",
		"validate": "sok_resdesk_governance.directory.check_ldap",
	},
	"Social Login Key": {
		"before_validate": "sok_resdesk_governance.directory.check_social_key",
		"validate": "sok_resdesk_governance.directory.check_social_key",
	},
	"RD Legal Hold": {
		"validate": "sok_resdesk_governance.retention.on_hold_validate",
		"on_update": "sok_resdesk_governance.retention.on_hold_change",
	},
	"RD Clearance": {
		"on_update": "sok_resdesk_governance.classification.on_clearance_change",
		"on_trash": "sok_resdesk_governance.classification.on_clearance_change",
	},
	"RD Settings": {"validate": "sok_resdesk_governance.classification.check_governance_switch"},
}

scheduler_events = {
	"daily": [
		# records whose retention period has ended are listed for the records officer
		"sok_resdesk_governance.retention.prepare",
		# LDAP accounts the directory no longer has are switched off
		"sok_resdesk_governance.directory.sync",
	]
}

# the records office in the Desk: roles, Help buttons, sidebar entries (desk.py)
resdesk_roles = ["sok_resdesk_governance.desk.roles"]
resdesk_screen_help = ["sok_resdesk_governance.desk.screen_help"]
boot_session = ["sok_resdesk_governance.desk.add_menu"]
after_install = "sok_resdesk_governance.desk.create_roles"
after_migrate = [*after_migrate, "sok_resdesk_governance.desk.create_roles"]
