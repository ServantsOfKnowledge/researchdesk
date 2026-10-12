import frappe


def execute():
	"""Mailed sign-in links lived 20 minutes (Frappe's default): make that a day, unless chosen otherwise."""
	from sok_resdesk import clock

	if clock.lengthen_default():
		frappe.db.commit()
