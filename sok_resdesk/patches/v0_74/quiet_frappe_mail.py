import frappe


def execute():
	"""Frappe's own notification emails off for every account (they stay in the Desk bell)."""
	from sok_resdesk import notifications

	notifications.quiet_everyone()
	frappe.db.commit()
