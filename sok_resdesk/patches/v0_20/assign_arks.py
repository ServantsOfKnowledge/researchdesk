def execute():
	"""Every book already in the catalogue gets its permanent ARK, oldest first (under the test NAAN
	until the library enters its own in Settings → Persistent Identifiers; they are then made again
	under it, keeping their names)."""
	from sok_resdesk.identifiers import assign_missing

	assign_missing()
