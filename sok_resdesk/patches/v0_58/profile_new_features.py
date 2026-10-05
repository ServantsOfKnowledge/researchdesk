def execute():
	"""0.58: manuscripts and photographs are features of the institutions that keep them. A library that
	chose its kinds of institution gets them as those kinds say (off unless a ticked kind includes
	them); a library that chose none keeps every feature on."""
	import frappe

	from sok_resdesk import features

	if not frappe.db.exists("DocType", "RD Settings"):
		return
	doc = frappe.get_single("RD Settings")
	keys = [k for k in features.PROFILES if doc.get(f"profile_{k}")]
	if not keys:
		return
	wanted, _preset = features.from_profiles(keys)
	for key in ("manuscripts", "photographs"):
		frappe.db.set_single_value("RD Settings", features.field_of(key), 1 if key in wanted else 0)
	features.apply()
