def execute():
	"""Books already in the catalogue get their ARK when the library switches ARKs on (Settings →
	Persistent Identifiers); this only matters for a site where they are on already."""
	from sok_resdesk.identifiers import assign_missing

	assign_missing()
