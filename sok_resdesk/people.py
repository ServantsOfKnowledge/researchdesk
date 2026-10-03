"""People and roles: who can do what in the library, on one Desk page (People & Roles).

Managers see each Research Desk role with its people, give or take a role with one click, invite
people by email (staff or readers), switch an account off or on, and decide sign-ups waiting
for approval. Frappe works out whether an account is staff (Desk) or portal-only from its
roles, so giving someone a staff role is all it takes to let them into the Desk.

Guard rails: only a System Manager gives or takes System Manager; nobody changes the
Administrator account or takes the manager role away from themselves (no lock-outs).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, get_fullname

from sok_resdesk.setup import DESK_ROLES, ROLES

MANAGERS = ("System Manager", "ResDesk Manager")
SYSTEM = "System Manager"
PROTECTED = ("Administrator", "Guest")


def managed_roles() -> list[str]:
	return [*ROLES, SYSTEM]


def _check_manager() -> None:
	frappe.only_for(MANAGERS)


def _check_role(role: str) -> None:
	if role not in managed_roles():
		frappe.throw(_("Research Desk doesn't manage the role {0} here.").format(role))
	if role == SYSTEM and SYSTEM not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager can give or take the System Manager role."), frappe.PermissionError
		)


def _check_user(user: str) -> None:
	if user in PROTECTED:
		frappe.throw(_("The {0} account can't be changed here.").format(user))
	if not frappe.db.exists("User", user):
		frappe.throw(_("No account {0}").format(user), frappe.DoesNotExistError)


def _holders(role: str) -> list[str]:
	return frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", distinct=True
	)


@frappe.whitelist()
def overview() -> dict:
	"""Each role with what it lets people do and how many have it; sign-ups waiting."""
	_check_manager()
	enabled = set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))
	roles = []
	for role in managed_roles():
		people = [u for u in _holders(role) if u in enabled and u not in PROTECTED]
		roles.append(
			{
				"role": role,
				"description": ROLES.get(role)
				or _("Everything in the Desk, including upgrades, restarts and backups."),
				"desk": role in DESK_ROLES or role == SYSTEM,
				"count": len(people),
				"can_grant": role != SYSTEM or SYSTEM in frappe.get_roles(),
			}
		)
	requests = frappe.get_all(
		"RD Reader Request",
		filters={"status": "Pending"},
		fields=["name", "user", "full_name", "email", "creation"],
		order_by="creation asc",
		limit=100,
	)
	for r in requests:
		r.creation = str(r.creation)[:16]
	return {"roles": roles, "requests": requests, "me": frappe.session.user}


@frappe.whitelist()
def users(role: str = "", q: str = "", show_disabled: int = 0, limit: int = 200) -> list[dict]:
	"""People with their Research Desk roles, newest first; filtered by a role or by name/email."""
	_check_manager()
	filters: dict = {"name": ("not in", PROTECTED)}
	if not cint(show_disabled):
		filters["enabled"] = 1
	if role:
		if role not in managed_roles():
			frappe.throw(_("Research Desk doesn't manage the role {0} here.").format(role))
		filters["name"] = ("in", _holders(role) or [""])
	or_filters = None
	if q and q.strip():
		like = f"%{q.strip()}%"
		or_filters = {"name": ("like", like), "full_name": ("like", like)}
	rows = frappe.get_all(
		"User",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "enabled", "user_type", "last_login", "creation"],
		order_by="creation desc",
		limit=max(1, min(cint(limit) or 200, 1000)),
	)
	if not rows:
		return []
	roles = frappe.get_all(
		"Has Role",
		filters={
			"parent": ("in", [r.name for r in rows]),
			"parenttype": "User",
			"role": ("in", managed_roles()),
		},
		fields=["parent", "role"],
	)
	by_user: dict[str, list[str]] = {}
	for r in roles:
		by_user.setdefault(r.parent, []).append(r.role)
	for r in rows:
		r.roles = sorted(set(by_user.get(r.name, [])))
		r.full_name = r.full_name or get_fullname(r.name)
		r.last_login = str(r.last_login)[:16] if r.last_login else ""
		r.creation = str(r.creation)[:10]
		r.desk = r.user_type == "System User"
	return rows


@frappe.whitelist(methods=["POST"])
def set_role(user: str, role: str, on: int = 1) -> dict:
	"""Give (on=1) or take (on=0) one role."""
	_check_manager()
	_check_user(user)
	_check_role(role)
	if not cint(on) and user == frappe.session.user and role in MANAGERS:
		frappe.throw(_("You can't take a manager role away from yourself: ask another manager."))
	doc = frappe.get_doc("User", user)
	doc.flags.ignore_permissions = True
	if cint(on):
		doc.add_roles(role)
	else:
		doc.remove_roles(role)
	return _person(user)


@frappe.whitelist(methods=["POST"])
def set_enabled(user: str, enabled: int = 1) -> dict:
	"""Switch an account off (it can't log in; its notes and work stay) or on again."""
	_check_manager()
	_check_user(user)
	if user == frappe.session.user:
		frappe.throw(_("You can't switch off your own account."))
	if SYSTEM in frappe.get_roles(user) and SYSTEM not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can switch a System Manager off."), frappe.PermissionError)
	frappe.db.set_value("User", user, "enabled", 1 if cint(enabled) else 0)
	frappe.clear_cache(user=user)
	return _person(user)


@frappe.whitelist(methods=["POST"])
def invite(emails: str, roles=None, full_name: str = "", send_welcome: int = 1) -> dict:
	"""Make accounts (or use existing ones) for one or more email addresses, with these roles."""
	_check_manager()
	roles = frappe.parse_json(roles) if isinstance(roles, str) else (roles or [])
	for role in roles:
		_check_role(role)
	if not roles:
		frappe.throw(_("Choose at least one role."))
	addresses = [e.strip().lower() for e in (emails or "").replace(",", "\n").splitlines() if e.strip()]
	if not addresses:
		frappe.throw(_("Give at least one email address."))
	if len(addresses) > 200:
		frappe.throw(_("At most 200 people at a time."))
	made, updated = [], []
	for email in addresses:
		frappe.utils.validate_email_address(email, throw=True)
		if email in PROTECTED:
			continue
		if frappe.db.exists("User", email):
			doc = frappe.get_doc("User", email)
			updated.append(email)
		else:
			name = full_name if len(addresses) == 1 and full_name else email.split("@")[0]
			first, _sep, last = name.partition(" ")
			doc = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first,
					"last_name": last,
					"user_type": "Website User",
					"send_welcome_email": 1 if cint(send_welcome) else 0,
				}
			)
			doc.flags.ignore_permissions = True
			doc.insert()
			made.append(email)
		doc.flags.ignore_permissions = True
		doc.add_roles(*roles)
	return {
		"made": made,
		"updated": updated,
		"message": _("{0} new accounts, {1} existing accounts given the roles.").format(
			len(made), len(updated)
		),
	}


@frappe.whitelist(methods=["POST"])
def decide(names, status: str) -> str:
	"""Approve or reject sign-ups waiting for approval."""
	from sok_resdesk.access import decide_requests

	return decide_requests(names, status)


def _person(user: str) -> dict:
	row = frappe.db.get_value(
		"User", user, ["name", "full_name", "enabled", "user_type", "last_login", "creation"], as_dict=True
	)
	row.roles = sorted(set(frappe.get_roles(user)) & set(managed_roles()))
	row.last_login = str(row.last_login)[:16] if row.last_login else ""
	row.creation = str(row.creation)[:10]
	row.desk = row.user_type == "System User"
	return row
