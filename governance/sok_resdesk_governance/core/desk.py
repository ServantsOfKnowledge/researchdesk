"""What the records-office app adds to the Desk, as data: its roles, Help buttons and sidebar entries
(sok_resdesk_governance/desk.py hands them to Research Desk). Pure Python, so it is unit-tested."""

from sok_resdesk.core import sidebar as layout

SECTION = "Running the Library"
AFTER = "Server"  # the entries follow this one

ROLES = {
	"ResDesk Security Officer": (
		"Governance Mode: grants clearances, keeps the departments and classifies records. Holds no other power over the catalogue.",
		True,
	),
	"ResDesk Records Officer": (
		"Retention rules, legal holds and disposal: approves what is disposed of when its period ends. Holds no clearance by role.",
		True,
	),
}

SCREEN_HELP = {
	"RD Audit Event": ("governance", "the-audit-log"),
	"RD Department": ("governance", "departments-and-clearances"),
	"RD Item Scope": ("governance", "where-the-level-and-department-live"),
	"RD Clearance": ("governance", "departments-and-clearances"),
	"RD File": ("governance", "file-register"),
	"RD Directory Account": ("governance", "directory-sign-in"),
	"RD Retention Rule": ("governance", "retention-and-legal-holds"),
	"RD Legal Hold": ("governance", "retention-and-legal-holds"),
	"RD Disposal": ("governance", "retention-and-legal-holds"),
	"RD Disclosure Request": ("governance", "disclosure-requests-and-redaction"),
}

D = layout.D
MENU = [
	("Audit Log", D, "RD Audit Event"),
	("Classified Records", D, "RD Item Scope"),
	("Departments", D, "RD Department"),
	("Clearances", D, "RD Clearance"),
	("File Register", D, "RD File"),
	("Directory Sign-ins", D, "RD Directory Account"),
	("Retention Rules", D, "RD Retention Rule"),
	("Legal Holds", D, "RD Legal Hold"),
	("Disposals", D, "RD Disposal"),
	("Disclosure Requests", D, "RD Disclosure Request"),
]


def inserted(items: list, links: list) -> list:
	"""`links` after the AFTER entry of the SECTION (at the section's end if that entry is absent)."""
	have = {(i.get("link_to") or i.get("url")) for i in items}
	links = [x for x in links if x["link_to"] not in have]
	in_section, at = False, None
	for n, item in enumerate(items):
		if item.get("type") == "Section Break":
			if in_section and at is None:
				at = n
			in_section = item.get("label") == SECTION
		elif in_section and item.get("label") == AFTER:
			at = n + 1
			break
	if at is None:
		at = len(items)
	return items[:at] + links + items[at:]
