import frappe


def execute():
	"""The portal's "N books" stopped at 10,000: the search engine only counted that far. Let the
	books index count them all (no re-index: this setting only changes how far a search counts)."""
	from sok_resdesk.search import BOOKS_MAX_HITS, MeiliClient, SearchError

	try:
		client = MeiliClient.from_settings()
		client._req(
			"PATCH",
			f"/indexes/{client.books}/settings",
			json={"pagination": {"maxTotalHits": BOOKS_MAX_HITS}},
		)
	except SearchError as e:
		if "index_not_found" in str(e):
			return  # nothing indexed yet: the first set-up of the index uses the new limit
		# the search engine isn't up during this migration: the next ingest run (or Settings →
		# Search → Set Up Search) applies it
		frappe.log_error("Research Desk: could not raise the book count limit yet", str(e))
