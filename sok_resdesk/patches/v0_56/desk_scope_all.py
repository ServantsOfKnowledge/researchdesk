def execute():
	"""0.56: Research Desk's sidebar holds every administrator's screen, so the default for the Desk is
	Research Desk only, for everyone: a library still on the old default (Administrator exempt) is moved
	to it. A library that chose another scope keeps its choice."""
	from sok_resdesk import deskscope

	if not frappe_db_ready():
		return
	import frappe

	current = frappe.db.get_single_value("RD Settings", "desk_scope")
	if not current or current == deskscope.EVERYONE:
		frappe.db.set_single_value("RD Settings", "desk_scope", deskscope.ALL)
	deskscope.apply_all()


def frappe_db_ready() -> bool:
	import frappe

	return bool(frappe.db.exists("DocType", "RD Settings"))
