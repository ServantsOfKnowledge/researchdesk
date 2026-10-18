"""What the records-office app adds to the Desk: its roles, Help buttons and sidebar entries.

Research Desk asks for these through hooks (resdesk_roles, resdesk_screen_help) and the boot below, so a
standard install carries none of them. The data is in core/desk.py.
"""

import frappe

from sok_resdesk.core import sidebar as layout
from sok_resdesk_governance.core import desk


def roles() -> dict:
	return desk.ROLES


def screen_help() -> dict:
	return desk.SCREEN_HELP


def add_menu(bootinfo) -> None:
	"""boot_session: the records office's screens join the Research Desk sidebar (both ways Frappe
	keeps sidebars: before and after 16.50), for the people who may open them."""
	if frappe.session.user == "Guest":
		return
	links = [
		layout._link(label, kind, target, child=1)
		for label, kind, target in desk.MENU
		if frappe.db.exists("DocType", target) and frappe.has_permission(target, "read")
	]
	if not links:
		return
	for payload in ("workspace_sidebar_item", "module_sidebars"):
		for key, sidebar in (bootinfo.get(payload) or {}).items():
			if str(key).lower() == layout.TITLE.lower() or sidebar.get("title") == layout.TITLE:
				sidebar["items"] = desk.inserted(list(sidebar.get("items") or []), links)


def create_roles() -> None:
	"""after_install / after_migrate: the officers' roles exist and work in the Desk."""
	from sok_resdesk.setup import create_roles as make

	make()
