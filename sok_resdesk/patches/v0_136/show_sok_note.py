import frappe


def execute():
	"""0.136: the About page's note about Servants of Knowledge is on unless a library unticks it. An About
	page saved before the box existed has no value for it: switch it on there once (a value already
	stored, ticked or not, is a choice and stays)."""
	if frappe.db.sql("select 1 from `tabSingles` where doctype = 'RD About Page' and field = 'show_sok'"):
		return
	frappe.db.set_single_value("RD About Page", "show_sok", 1)
