import frappe


def execute():
	"""Books First Automatically is on by default; an existing site gets it on too (a new setting's
	default is only stored when Settings are saved)."""
	if frappe.db.get_single_value("RD Settings", "auto_books_first") in (None, ""):
		frappe.db.set_single_value("RD Settings", "auto_books_first", 1)
