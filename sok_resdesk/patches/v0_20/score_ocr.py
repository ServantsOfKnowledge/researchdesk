import frappe


def execute():
	"""Score the OCR quality of the books already in the catalogue, in the background, from the page
	text kept on this server (no archive.org requests)."""
	from sok_resdesk.ocr import queue_scoring

	try:
		queue_scoring()
	except Exception:
		# the queue isn't reachable during this migration: the daily job does it instead
		frappe.log_error(title="Research Desk: OCR scoring will start with the daily job")
