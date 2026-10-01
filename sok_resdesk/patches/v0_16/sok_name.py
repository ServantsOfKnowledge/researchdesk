import frappe

OLD, NEW = "SoK", "SOK"


def execute():
	"""SOK, not SoK: the portal name, the starter profiles and the About page's starting text, where
	they still have the name Research Desk gave them."""
	settings = frappe.get_single("RD Settings")
	changed = False
	for field in ("portal_title", "portal_tagline"):
		value = settings.get(field) or ""
		if f"{OLD} Research Desk" in value:
			settings.set(field, value.replace(f"{OLD} Research Desk", f"{NEW} Research Desk"))
			changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()  # also renames it in the top bar and the browser tab (apply_branding)

	for old in (f"{OLD} Kannada sample", f"{OLD} English sample"):
		new = old.replace(OLD, NEW, 1)
		# names compare without case in MariaDB, so look for the exact spelling
		exact = frappe.db.sql("select name from `tabRD Ingest Profile` where binary name=%s", old)
		taken = frappe.db.sql("select name from `tabRD Ingest Profile` where binary name=%s", new)
		if exact and not taken:
			frappe.rename_doc("RD Ingest Profile", old, new, force=True)
			frappe.db.set_value("RD Ingest Profile", new, "profile_name", new)

	if frappe.db.exists("DocType", "RD About Page"):
		intro = frappe.db.get_single_value("RD About Page", "intro") or ""
		if f"{OLD} Research Desk" in intro:
			frappe.db.set_single_value(
				"RD About Page", "intro", intro.replace(f"{OLD} Research Desk", f"{NEW} Research Desk")
			)
