"""v0.7: document types and curated collections. Existing items become Books."""

import frappe


def execute():
	frappe.db.sql("update `tabRD Item` set item_type='Book' where ifnull(item_type, '') = ''")
	# search documents gain collection/type/subject fields: run `./resdesk.sh reindex --background`
	# so page search can filter by them (book search works straight away after migrate).
