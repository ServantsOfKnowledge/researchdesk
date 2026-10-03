import frappe


def execute():
	"""Check every book's page order against its scan data, in the background (page_order.py)."""
	from sok_resdesk.page_order import queue_fixing

	try:
		queue_fixing()
	except Exception:
		# the queue isn't reachable during this migration: the daily job does it instead
		frappe.log_error(title="Research Desk: the page order check will start with the daily job")
