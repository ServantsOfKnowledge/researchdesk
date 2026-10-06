"""The Research Desk sidebar's structure, as data: sections and screens, and the items made from it.

Pure Python (no Frappe), so it is unit-tested and so scripts/make_sidebar_json.py can write the
sidebar Frappe 16.50 and later ship from the same list. sok_resdesk/sidebar.py applies it.

Each entry is (label, link type, target, icon). A section is ("section", label, icon, [entries]).
"""

from __future__ import annotations

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
			("Archival Description", D, "RD Archival Unit"),
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
			("Connections", P, "resdesk-connections"),
			("Exports", D, "RD Export"),
			("Metadata Imports", D, "RD Metadata Import"),
			("Library Systems", D, "RD Library System"),
			("Library Records", D, "RD Library Record"),
			("Push Targets", D, "RD Push Target"),
			("Push Runs", D, "RD Push Run"),
			("External Records", D, "RD External Record"),
			("My Wikimedia Account", D, "RD Wikimedia Account"),
			("My archive.org Account", D, "RD Archive Account"),
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
			("My Release for Ground Truth", D, "RD Contributor Release"),
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
			("Portal Translations", P, "resdesk-translations"),
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


def build(hidden: set[str] | None = None, exists=None) -> list[dict]:
	"""The sidebar's items, less the screens in `hidden` (those of switched-off features), less
	targets `exists(kind, target)` says this site does not have, and less any section left empty."""
	hidden = hidden or set()
	exists = exists or (lambda kind, target: True)

	def present(kind: str, target: str) -> bool:
		return target not in hidden and exists(kind, target)

	out: list[dict] = []
	for entry in STRUCTURE:
		if entry[0] == "section":
			_kind, label, icon, children = entry
			kept = [c for c in children if present(c[1], c[2])]
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
