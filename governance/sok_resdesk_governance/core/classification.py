"""Classification levels and need-to-know: who is cleared for a record. Pure Python, no Frappe.

A record has a level and, optionally, a department. A person has a clearance: the highest level
they may see and the departments they belong to. The department tree is read downward: a head
office sees its subordinate offices' records, a taluk office sees only its own. A record with no
department is open to anyone cleared for its level.
"""

from __future__ import annotations

LEVELS = ("Unclassified", "Restricted", "Confidential", "Secret", "Top Secret")
STANDARD_LEVELS = LEVELS[:3]  # the top two need Classified mode (resdesk_classified in the site config)


def rank(level: str | None) -> int:
	return LEVELS.index(level) if level in LEVELS else 0


def allowed_levels(classified_mode: bool) -> tuple[str, ...]:
	return LEVELS if classified_mode else STANDARD_LEVELS


def expand(departments, parents: dict[str, str]) -> set[str]:
	"""`departments` and every office below them. `parents` maps a department to its parent."""
	held = {d for d in departments if d}
	changed = True
	while changed:
		changed = False
		for child, parent in parents.items():
			if parent in held and child not in held:
				held.add(child)
				changed = True
	return held


def cleared(
	user_rank: int, user_departments: set[str] | None, item_rank: int, item_department: str | None
) -> bool:
	"""`user_departments` None means every department (the built-in Administrator)."""
	if item_rank > user_rank:
		return False
	return not item_department or user_departments is None or item_department in user_departments


def meili_clause(user_rank: int, user_departments: set[str] | None) -> str:
	"""Meilisearch filter for the records a person is cleared for (documents lacking the fields count
	as level 0 with no department)."""
	parts = [f"NOT class_rank > {int(user_rank)}"]
	if user_departments is not None:
		names = ", ".join(
			'"' + d.replace("\\", "\\\\").replace('"', '\\"') + '"' for d in sorted(user_departments)
		)
		parts.append(
			"(department IS EMPTY OR department IS NULL" + (f" OR department IN [{names}])" if names else ")")
		)
	return "(" + " AND ".join(parts) + ")"


def sql_clause(user_rank: int, user_departments: set[str] | None, prefix: str, quote) -> str:
	"""The same as an SQL fragment; `quote` escapes a value, `prefix` is the table alias with its dot."""
	parts = [f"ifnull({prefix}class_rank, 0) <= {int(user_rank)}"]
	if user_departments is not None:
		inside = ", ".join(quote(d) for d in sorted(user_departments))
		parts.append(
			f"(ifnull({prefix}department, '') = ''"
			+ (f" or {prefix}department in ({inside}))" if inside else ")")
		)
	return "(" + " and ".join(parts) + ")"
