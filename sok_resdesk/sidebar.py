"""The Desk's sidebar: every Research Desk screen, and the administrator's tools, in one place.

The list itself is core/sidebar.py. How Frappe 16 takes it depends on the release:

* **Frappe 16.50 and later** keep a module's sidebar as a ``Sidebar`` document that an app ships as
  JSON (``resdesk/sidebar/research_desk/research_desk.json``, written by
  ``scripts/make_sidebar_json.py`` from the same list) and no longer let an app edit it on a site.
  The shipped sidebar holds every screen; a switched-off feature's screens are taken out of what
  the Desk is sent (features.trim_boot).
* **Earlier Frappe 16** builds it from a *Workspace Sidebar* document, which :func:`refresh`
  rewrites to the list, less switched-off features' screens (trim_boot takes them out as well).

Either way Frappe filters each entry by what the signed-in person may open, so the *Administration*
section (users, roles, system settings, logs…) only shows for those who may use those screens, and
library staff see the library's screens alone (:func:`trim_boot` makes sure).
"""

from __future__ import annotations

import frappe

from sok_resdesk.core import sidebar as core
from sok_resdesk.core.sidebar import STRUCTURE, TITLE, D, P, W  # noqa: F401  (re-exported)

MODULE = "ResDesk"  # the module the shipped Sidebar belongs to (Frappe 16.50 and later)


def items(hidden: set[str] | None = None) -> list[dict]:
	"""The sidebar's items, less the screens in `hidden` (those of switched-off features), less
	targets this site does not have, and less any section left empty."""

	def exists(kind: str, target: str) -> bool:
		if kind == D:
			return bool(frappe.db.exists("DocType", target))
		if kind == P:
			return bool(frappe.db.exists("Page", target))
		return True  # a workspace, or an address

	return core.build(hidden, exists)


def _site_layers() -> bool:
	"""Whether this Frappe keeps sidebars as shipped Sidebar documents (16.50 and later)."""
	return bool(frappe.db.exists("DocType", "Custom Sidebar")) and bool(
		frappe.db.exists("DocType", "Sidebar")
	)


def refresh() -> None:
	"""Make the Desk's "Research Desk" sidebar the shipped one, less switched-off features' screens."""
	from sok_resdesk import features

	if _site_layers():  # from 16.50 the shipped Sidebar is the sidebar
		_drop_leftover_module()
	else:
		_refresh_workspace_sidebar(features.hidden_targets())
	frappe.cache.delete_key("bootinfo")
	frappe.clear_cache()


def _drop_leftover_module() -> None:
	"""Frappe 16.50 turned our old Workspace Sidebar into a site module called "Research Desk". The
	shipped Sidebar has that name too (it belongs to the ResDesk module), and an empty module of the
	same name would shadow it, so the leftover goes."""
	if not frappe.db.exists("Module Def", TITLE) or frappe.db.get_value("Module Def", TITLE, "custom") != 1:
		return
	for doctype in ("Workspace", "Page", "Report", "DocType"):
		if frappe.db.exists(doctype, {"module": TITLE}):
			return
	try:
		frappe.delete_doc("Module Def", TITLE, force=True, ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Research Desk: the leftover Research Desk module was not removed")


def _refresh_workspace_sidebar(hidden: set[str]) -> None:
	"""Earlier Frappe 16: rewrite the Workspace Sidebar to the list."""
	wanted = items(hidden)
	if frappe.db.exists("Workspace Sidebar", TITLE):
		doc = frappe.get_doc("Workspace Sidebar", TITLE)
		same = [(i.type, i.label, i.link_to or i.url, i.child) for i in doc.items] == [
			(w["type"], w["label"], w.get("link_to") or w.get("url"), w.get("child", 0)) for w in wanted
		]
		if same:
			return
	else:
		doc = frappe.new_doc("Workspace Sidebar")
		doc.title = TITLE
		doc.header_icon = "book"
		doc.module = MODULE
	doc.set("items", wanted)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.save() if not doc.is_new() else doc.insert()


def trim_boot(bootinfo) -> None:
	"""The Administration section (Frappe's own tools) is for System Managers; library staff keep the
	library's screens alone, whatever Frappe would let their roles read."""
	if "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator":
		return
	for payload in ("workspace_sidebar_item", "module_sidebars"):  # before and after Frappe 16.50
		sidebars = bootinfo.get(payload) or {}
		for key, sidebar in list(sidebars.items()):
			kept, skipping = [], False
			for item in sidebar.get("items") or []:
				if item.get("type") == "Section Break":
					skipping = item.get("label") == "Administration"
				if not skipping:
					kept.append(item)
			if len(kept) != len(sidebar.get("items") or []):
				sidebars[key] = {**sidebar, "items": kept}


def brand_boot(bootinfo) -> None:
	"""The library's own logo on the Desk's app icon (Frappe 16.50 and later take it from the app's
	entry in the apps list, which the app's hooks fix to the default; the library's logo from
	Settings → Portal replaces it, as it does the portal's)."""
	if frappe.session.user == "Guest":
		return
	logo = frappe.db.get_single_value("RD Settings", "favicon") or frappe.db.get_single_value(
		"RD Settings", "portal_logo"
	)
	if not logo:
		return
	for app in bootinfo.get("app_data") or []:
		if app.get("app_name") == "sok_resdesk":
			app["app_logo_url"] = logo
