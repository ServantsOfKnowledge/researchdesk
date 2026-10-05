def execute():
	"""0.64: archival description is a feature of the archives and repositories that keep papers. A
	library that chose its kinds gets it as they say; one that chose none keeps every feature on."""
	import frappe

	from sok_resdesk import features

	if not frappe.db.exists("DocType", "RD Settings"):
		return
	doc = frappe.get_single("RD Settings")
	keys = [k for k in features.PROFILES if doc.get(f"profile_{k}")]
	if not keys:
		return
	wanted, _preset = features.from_profiles(keys)
	frappe.db.set_single_value("RD Settings", features.field_of("archival"), 1 if "archival" in wanted else 0)
	features.apply()
