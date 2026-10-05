"""The Desk's sidebar: every Research Desk screen, and the administrator's tools, in one place.

Frappe 16 builds the sidebar from a *Workspace Sidebar* document. This keeps ours, "Research Desk",
as the shipped list below (rebuilt on every upgrade and whenever a feature is switched on or off,
so a switched-off feature's screens leave it). Frappe filters each entry by what the signed-in
person may open, so the *Administration* section (users, roles, system settings, logs…) only
shows for those who may use those screens, and library staff see the library's screens alone.

Each entry is (label, link type, target, icon). A section is ("section", label, icon, [entries]).
"""

from __future__ import annotations

import frappe

TITLE = "Research Desk"
D, P, W = "DocType", "Page", "Workspace"

STRUCTURE: list = [
	("Home", W, "Research Desk", "home"),
	(
		"section",
		"Catalogue",
		"library",
		[
			("Ingest Profiles", D, "RD Ingest Profile"),
			("Ingest Runs", D, "RD Ingest Run"),
			("Items", D, "RD Item"),
			("Collections", D, "RD Collection"),
			("Deposits", D, "RD Deposit"),
			("Review Queue", P, "resdesk-review"),
			("Authorities", P, "resdesk-authorities"),
		],
	),
	(
		"section",
		"Exchange",
		"arrow-left-right",
		[
			("Exports", D, "RD Export"),
			("Metadata Imports", D, "RD Metadata Import"),
			("Library Systems", D, "RD Library System"),
			("Library Records", D, "RD Library Record"),
			("Push Targets", D, "RD Push Target"),
			("Push Runs", D, "RD Push Run"),
			("External Records", D, "RD External Record"),
			("My Wikimedia Account", D, "RD Wikimedia Account"),
		],
	),
	(
		"section",
		"Readers and Research",
		"users",
		[
			("Reader Requests", D, "RD Reader Request"),
			("Research Groups", D, "RD Research Group"),
			("Notes", D, "RD Annotation"),
			("Page Text Versions", D, "RD Page Text"),
			("Ground Truth", D, "RD Ground Truth"),
		],
	),
	(
		"section",
		"Keeping",
		"archive",
		[
			("Preservation Events", D, "RD Preservation Event"),
			("Tombstones", D, "RD Tombstone"),
		],
	),
	(
		"section",
		"Running the Library",
		"settings",
		[
			("Background Jobs", P, "resdesk-jobs"),
			("Server", P, "resdesk-server"),
			("Open Portal", "URL", "/"),
			("Settings", D, "RD Settings"),
			("About Page", D, "RD About Page"),
			("People & Roles", P, "resdesk-people"),
			("Help", P, "resdesk-help"),
		],
	),
	(
		"section",
		"Administration",
		"wrench",
		[
			("Users", D, "User"),
			("Roles", D, "Role"),
			("User Permissions", D, "User Permission"),
			("Permission Manager", P, "permission-manager"),
			("System Settings", D, "System Settings"),
			("Email Accounts", D, "Email Account"),
			("Email Queue", D, "Email Queue"),
			("Error Log", D, "Error Log"),
			("Scheduled Job Log", D, "Scheduled Job Log"),
			("Access Log", D, "Access Log"),
			("Files", D, "File"),
			("Translations", D, "Translation"),
			("Module Profiles", D, "Module Profile"),
			("Data Import", D, "Data Import"),
		],
	),
]


def items(hidden: set[str] | None = None) -> list[dict]:
	"""The sidebar's items, less the screens in `hidden` (those of switched-off features), less
	targets this site does not have, and less any section left empty."""
	hidden = hidden or set()

	def exists(kind: str, target: str) -> bool:
		if target in hidden:
			return False
		if kind == D:
			return bool(frappe.db.exists("DocType", target))
		if kind == P:
			return bool(frappe.db.exists("Page", target))
		return True  # a workspace, or an address

	out: list[dict] = []
	for entry in STRUCTURE:
		if entry[0] == "section":
			_kind, label, icon, children = entry
			kept = [c for c in children if exists(c[1], c[2])]
			if not kept:
				continue
			out.append(
				{
					"type": "Section Break",
					"label": label,
					"icon": icon,
					"indent": 1,
					"collapsible": 1,
					"keep_closed": 1 if label == "Administration" else 0,
				}
			)
			out += [_link(lbl, kind, to, child=1) for lbl, kind, to in kept]
		else:
			lbl, kind, to, icon = entry
			out.append(_link(lbl, kind, to, icon=icon))
	return out


def _link(label: str, kind: str, target: str, child: int = 0, icon: str = "") -> dict:
	if kind == "URL":
		return {
			"type": "Link",
			"label": label,
			"link_type": "URL",
			"url": target,
			"child": child,
			"icon": icon,
		}
	return {
		"type": "Link",
		"label": label,
		"link_type": kind,
		"link_to": target,
		"child": child,
		"icon": icon,
	}


def refresh() -> None:
	"""Make the Desk's "Research Desk" sidebar the shipped one (see items)."""
	from sok_resdesk import features

	wanted = items(features.hidden_targets())
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
		doc.module = "ResDesk"
	doc.set("items", wanted)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.save() if not doc.is_new() else doc.insert()
	frappe.cache.delete_key("bootinfo")
	frappe.clear_cache()


def trim_boot(bootinfo) -> None:
	"""The Administration section (Frappe's own tools) is for System Managers; library staff keep the
	library's screens alone, whatever Frappe would let their roles read."""
	if "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator":
		return
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	for key, sidebar in list(sidebars.items()):
		kept, skipping = [], False
		for item in sidebar.get("items") or []:
			if item.get("type") == "Section Break":
				skipping = item.get("label") == "Administration"
			if not skipping:
				kept.append(item)
		if len(kept) != len(sidebar.get("items") or []):
			sidebars[key] = {**sidebar, "items": kept}
