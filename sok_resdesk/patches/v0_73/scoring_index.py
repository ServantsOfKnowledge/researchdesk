import frappe


def execute():
	"""Finding the books still to score (and the watchdog asking every ten minutes) read three fields
	of every book; an index lets the database answer without walking the whole table."""
	frappe.db.add_index("RD Item", ["has_page_text", "ocr_quality", "ocr_low_pages"])
