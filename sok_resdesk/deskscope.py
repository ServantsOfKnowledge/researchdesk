"""The Desk shows Research Desk, and only Research Desk (Settings → Readers & Access → The Desk).

Frappe's own workspaces (Build, Users, Website, Integrations and the rest) are for whoever runs
Frappe itself; librarians, cataloguers and the library's administrators work in Research Desk.
A Module Profile, *Research Desk only*, hides every other module from the Desk's sidebar, its
app screen and its search; everyone lands in Research Desk. Nothing about what a person may open
changes (roles decide that): Users, for instance, stays reachable from Research Desk → People.

By default this holds for the built-in Administrator account too: Frappe's own screens that an
administrator needs (users, roles, system settings, logs…) are in Research Desk's sidebar, under
*Administration*, so nobody has to find their way back from Frappe's own desktop. Settings → The
Desk can give Administrator (or every System Manager) Frappe's desktop back.
"""

from __future__ import annotations

import frappe

PROFILE = "Research Desk only"
KEEP = ("ResDesk",)
APP = "sok_resdesk"
STAFF_ROLES = ("ResDesk Manager", "ResDesk Cataloguer", "ResDesk Proofreader", "System Manager")
ALL = "Research Desk only, for everyone (Frappe's tools are under Administration)"
EVERYONE = "Research Desk only, except Administrator"
STAFF = "Research Desk only for staff; System Managers see everything"
OFF = "Everything (Frappe's own tools too)"


def scope() -> str:
	return frappe.db.get_single_value("RD Settings", "desk_scope") or ALL


def ensure_profile() -> str:
	"""The Module Profile, blocking every module but Research Desk's (new modules included)."""
	modules = frappe.get_all("Module Def", pluck="name")
	doc = frappe.get_doc("Module Profile", PROFILE) if frappe.db.exists("Module Profile", PROFILE) else None
	if doc is None:
		doc = frappe.new_doc("Module Profile")
		doc.module_profile_name = PROFILE
	blocked = sorted(m for m in modules if m not in KEEP)
	if sorted(r.module for r in doc.get("block_modules") or []) != blocked:
		doc.set("block_modules", [{"module": m} for m in blocked])
		doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
	return doc.name


def applies_to(user) -> bool:
	"""Whether this Desk user sees only Research Desk."""
	if user.name in ("Administrator", "Guest") or user.user_type != "System User":
		return False
	how = scope()
	if how == OFF:
		return False
	roles = {r.role for r in user.get("roles") or []}
	if how == STAFF and "System Manager" in roles:
		return False
	return bool(roles & set(STAFF_ROLES))


def before_validate(doc, method=None):
	"""User: the profile follows the setting and the person's roles (doc_events)."""
	if frappe.flags.in_install or not frappe.db.exists("DocType", "RD Settings"):
		return
	if applies_to(doc):
		doc.module_profile = ensure_profile()
		if not doc.default_workspace and frappe.db.exists("Workspace", "Research Desk"):
			doc.default_workspace = "Research Desk"
		if doc.meta.has_field("default_app") and not doc.default_app:
			doc.default_app = APP
	elif doc.module_profile == PROFILE:
		doc.module_profile = None
		doc.set("block_modules", [])


def trim_boot(bootinfo):
	"""The apps screen and its sidebars: Frappe 16 builds them from Workspace Sidebars and app
	icons, not from blocked modules, so for these users only Research Desk's are kept."""
	user = frappe.session.user
	if user == "Guest":
		return
	admin_too = user == "Administrator" and scope() == ALL
	if not admin_too and frappe.db.get_value("User", user, "module_profile") != PROFILE:
		return
	bootinfo.resdesk_desk_only = True  # desk_only.js keeps the way back to Frappe's desktop closed
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	bootinfo.workspace_sidebar_item = {
		k: v for k, v in sidebars.items() if not v.get("module") or v.get("module") in KEEP
	}
	icons = bootinfo.get("desktop_icons") or []
	kept = {i.label for i in icons if i.get("app") == APP and not i.get("parent_icon")}
	bootinfo.desktop_icons = [i for i in icons if i.label in kept or i.get("parent_icon") in kept]


def apply_all() -> int:
	"""Every Desk user, after the setting changes or an upgrade (new modules)."""
	ensure_profile()
	changed = 0
	for name in frappe.get_all("User", filters={"user_type": "System User", "enabled": 1}, pluck="name"):
		if name in ("Administrator", "Guest"):
			continue
		user = frappe.get_doc("User", name)
		wanted = PROFILE if applies_to(user) else None
		if (user.module_profile or None) != wanted or (wanted and not user.block_modules):
			user.flags.ignore_permissions = True
			user.save(ignore_permissions=True)  # before_validate sets the profile and its blocks
			changed += 1
	if scope() != OFF:
		frappe.db.set_single_value("System Settings", "default_app", APP)
	frappe.clear_cache()
	return changed


def after_migrate() -> None:
	try:
		apply_all()
	except Exception:
		frappe.log_error(title="Research Desk: the Desk's scope was not applied")
