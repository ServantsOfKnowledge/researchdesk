import frappe


def execute():
	"""0.123: the Sort menu's Recently added and Author A–Z read two new fields of each book's search
	record. Send the book records again, in the background (page text is not touched)."""
	try:
		from sok_resdesk.search import queue_rebuild

		queue_rebuild(with_pages=0)
	except Exception:
		# no search engine at upgrade time: Settings → Search Engine → Rebuild does it later
		frappe.log_error(title="Research Desk: could not queue the search records for the new sort orders")
