"""v0.2: defaults for parallel ingest and the page-text cache on existing sites."""

import frappe


def execute():
	s = frappe.get_single("RD Settings")
	changed = False
	if not s.batch_size:
		s.batch_size = 50
		changed = True
	# New in v0.2: sites created earlier have 0 stored, not the field default, so switch it on.
	if not s.cache_page_text:
		s.cache_page_text = 1
		changed = True
	if changed:
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)
