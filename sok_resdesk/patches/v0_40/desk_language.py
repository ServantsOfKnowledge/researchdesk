import frappe


def execute():
	"""Staff whose account language was set by the portal's language switch (before 0.40) get the
	Desk in the site's language again. Readers (website users) keep theirs: it is only theirs."""
	from sok_resdesk.translations import portal_languages

	langs = portal_languages()
	if not langs:
		return
	staff = frappe.get_all(
		"User",
		filters={"user_type": "System User", "language": ("in", langs), "name": ("not in", ("Guest",))},
		pluck="name",
	)
	for name in staff:
		frappe.db.set_value("User", name, "language", "", update_modified=False)
		frappe.clear_cache(user=name)
