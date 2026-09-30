"""v0.11: defaults for the new Server & Updates settings on existing installs."""

import frappe


def execute():
	for field, value in (
		("check_updates", 1),
		("allow_desk_upgrades", 1),
		("backup_schedule", "Daily"),
		("backup_keep", 7),
		("alert_email", 1),
		("alert_disk_percent", 90),
	):
		stored = frappe.db.get_singles_dict("RD Settings").get(field)
		if stored in (None, ""):
			frappe.db.set_single_value("RD Settings", field, value)
