"""v0.11: profiles from archive.org are kept in step with it from now on. Their last completed
run is where they are in step up to, so the first daily sync brings only what changed since."""

import frappe


def execute():
	for name in frappe.get_all(
		"RD Ingest Profile",
		filters={"source": "Internet Archive", "synced_on": ("is", "not set")},
		pluck="name",
	):
		last = frappe.get_all(
			"RD Ingest Run",
			filters={"profile": name, "status": ("in", ["Completed", "Completed with Errors"])},
			fields=["started_on", "creation"],
			order_by="creation desc",
			limit=1,
		)
		if last:
			frappe.db.set_value(
				"RD Ingest Profile",
				name,
				"synced_on",
				last[0].started_on or last[0].creation,
				update_modified=False,
			)
