import frappe


def execute():
	"""The library's search page lives at / (the site's home page): links that said /library now
	say /. /library itself keeps working (it sends visitors to /)."""
	from sok_resdesk.portal import library_url

	if library_url() != "/":
		return  # the site has another home page: the library stays at /library
	ws = frappe.get_single("Website Settings")
	changed = False
	for item in ws.top_bar_items:
		if (item.url or "").rstrip("/") == "/library":
			item.url = "/"
			changed = True
	if changed:
		ws.flags.ignore_permissions = True
		ws.save()
	if frappe.db.exists("DocType", "RD About Page"):
		about = frappe.get_single("RD About Page")
		dirty = False
		if (about.primary_link or "").rstrip("/") == "/library":
			about.primary_link = "/"
			dirty = True
		for row in about.steps + about.highlights:
			if (row.link or "").rstrip("/") == "/library":
				row.link = "/"
				dirty = True
		if dirty:
			about.flags.ignore_permissions = True
			about.save()
	from frappe.website.utils import clear_cache

	clear_cache()
