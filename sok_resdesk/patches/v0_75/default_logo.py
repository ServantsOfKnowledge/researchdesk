def execute():
	"""The Servants of Knowledge logo for a library that never set its own (portal, top bar, Desk)."""
	import frappe

	from sok_resdesk.setup import ensure_default_logo

	ensure_default_logo()
	frappe.db.commit()
