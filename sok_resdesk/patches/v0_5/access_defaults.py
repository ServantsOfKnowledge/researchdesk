"""v0.5: access control. Existing books stay Public; the site stays open to guests."""

import frappe


def execute():
	# the new column is created with its default (Public) already filled in
	frappe.db.sql("update `tabRD Item` set visibility='Public' where ifnull(visibility, '') = ''")
	frappe.db.sql("update `tabRD Item` set visibility_set_by='Default' where ifnull(visibility_set_by, '') = ''")
	for field, value in (
		("guest_access", "Each item's setting"),
		("default_visibility", "Public"),
		("reader_signup", "Admins add readers"),
		("oai_scope", "Records guests can find"),
	):
		if not frappe.db.get_single_value("RD Settings", field):
			frappe.db.set_single_value("RD Settings", field, value)
	# existing search documents have no visibility field and count as Public, so no re-index
	# is needed; after_migrate adds "visibility" to the filterable attributes.
