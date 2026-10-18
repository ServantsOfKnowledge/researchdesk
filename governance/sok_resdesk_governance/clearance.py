"""Clearance: who may see classified records (docs/governance.md). The governance layer's half of access.

Core (access.py) asks only through seams.py, so a library without governance never loads this. The
functions here are registered as hooks in hooks.py (resdesk_governed, resdesk_item_cleared,
resdesk_cleared_sql, resdesk_search_clause) and as permission conditions for the governance doctypes.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from sok_resdesk import access
from sok_resdesk_governance.core import classification as levels


def clearance(user: str | None = None) -> tuple[int, set[str] | None]:
	"""(highest level number, departments incl. the offices below them). None = every department.
	Nobody holds a clearance by role: not even a System Manager. Only the built-in Administrator
	sees all, and that is in the audit log. No clearance record: Unclassified, no department."""
	user = user or frappe.session.user
	if user == "Administrator":
		return len(levels.LEVELS) - 1, None
	cache = getattr(frappe.local, "rd_clearance", None)
	if cache is None:
		cache = frappe.local.rd_clearance = {}
	if user not in cache:
		row = frappe.db.get_value("RD Clearance", user, "name") if user != "Guest" else None
		if not row:
			cache[user] = (0, set())
		else:
			doc = frappe.get_doc("RD Clearance", user)  # not cached: a revoked clearance must stop at once
			parents = dict(
				frappe.db.sql(
					"select name, parent_department from `tabRD Department` where ifnull(parent_department, '') != ''"
				)
			)
			cache[user] = (
				levels.rank(doc.level),
				levels.expand([d.department for d in doc.departments], parents),
			)
	return cache[user]


def scope_of(item: str | None) -> tuple[int, str]:
	"""(level number, department) of a classified record; (0, "") when it has no line in RD Item Scope."""
	row = frappe.db.get_value("RD Item Scope", item, ["class_rank", "department"]) if item else None
	return (cint(row[0]), row[1] or "") if row else (0, "")


def is_cleared(class_rank, department, user: str | None = None) -> bool:
	rank, departments = clearance(user)
	return levels.cleared(rank, departments, cint(class_rank), department)


def cleared_sql(item_expr: str, user: str | None = None) -> str:
	"""SQL: the item (named by `item_expr`) has a scope this person is cleared for."""
	rank, departments = clearance(user)
	mine = levels.sql_clause(rank, departments, "s.", frappe.db.escape)
	return f"exists (select 1 from `tabRD Item Scope` s where s.name = {item_expr} and {mine})"


def scope_conditions(user: str | None = None) -> str:
	"""The Desk's list of classified records is itself only what the person is cleared for."""
	if not access.governed():
		return "1=0"
	rank, departments = clearance(user)
	return levels.sql_clause(rank, departments, "`tabRD Item Scope`.", frappe.db.escape)


def scope_has_permission(doc, ptype=None, user=None):
	if not (access.governed() and is_cleared(doc.get("class_rank"), doc.get("department"), user)):
		return False
	return None


def file_conditions(user: str | None = None) -> str:
	"""The file register: a person sees the files they are cleared for (whether or not Governance Mode is
	on: a file with a level or a department stays hidden from anyone without a clearance)."""
	rank, departments = clearance(user)
	return levels.sql_clause(rank, departments, "`tabRD File`.", frappe.db.escape)


def file_has_permission(doc, ptype=None, user=None):
	return bool(is_cleared(doc.get("class_rank"), doc.get("department"), user))


def _of_file(table: str, user: str | None) -> str:
	"""The rows of a file's tables (records, movements) are read only with the file: Frappe checks a
	child table against its parent's role alone, so the file's own rule is repeated here."""
	rank, departments = clearance(user)
	cleared = levels.sql_clause(rank, departments, "f.", frappe.db.escape)
	return f"`tab{table}`.parent in (select f.name from `tabRD File` f where {cleared})"


def file_record_conditions(user=None):
	return _of_file("RD File Record", user)


def file_movement_conditions(user=None):
	return _of_file("RD File Movement", user)


def _unseen_items(request: str, user: str | None) -> str:
	"""SQL: the request (named by `request`) lists a record this person may not see."""
	seen = access.item_condition("i", user)
	return (
		"exists (select 1 from `tabRD Disclosure Record` r join `tabRD Item` i on i.name = r.item "
		f"where r.parent = {request} and not ({seen}))"
	)


def disclosure_conditions(user=None):
	"""A disclosure request is seen only by someone who may see every record it names."""
	return f"not {_unseen_items('`tabRD Disclosure Request`.name', user)}"


def disclosure_has_permission(doc, ptype=None, user=None):
	return all(
		frappe.db.exists("RD Item", r.item) and is_cleared(*scope_of(r.item), user=user)
		for r in doc.get("records") or []
	)


def _of_request(table: str, user: str | None) -> str:
	"""A request's rows are read only with the request (Frappe checks a child table by role alone)."""
	return (
		f"`tab{table}`.parent in (select q.name from `tabRD Disclosure Request` q "
		f"where not {_unseen_items('q.name', user)})"
	)


def disclosure_record_conditions(user=None):
	return _of_request("RD Disclosure Record", user)


def disclosure_redaction_conditions(user=None):
	return _of_request("RD Disclosure Redaction", user)


def item_cleared(item: str | None, user: str | None = None) -> bool:
	"""Hook resdesk_item_cleared: this person is cleared for the record's level and department."""
	return is_cleared(*scope_of(item), user)


def search_clause() -> str:
	"""Hook resdesk_search_clause: the search engine's filter for the records this person is cleared for."""
	return levels.meili_clause(*clearance())
