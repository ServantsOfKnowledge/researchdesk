import frappe


def execute():
	"""Native installs stored book folders as real paths (/Users/…/library/…). Store them as
	/library-source/… like Docker does, so the catalogue can move to another server or to Docker."""
	from sok_resdesk.local_source import DEFAULT_ROOT, library_dir, relink

	real = library_dir()
	if real and real.rstrip("/") != DEFAULT_ROOT:
		relink(real, DEFAULT_ROOT)
	frappe.db.commit()
