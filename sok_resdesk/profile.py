"""About me: what a person chose to tell the library, kept simple and optional.

Anyone signed in can describe themselves (a person or an organisation), say whether they would
like to help as a reviewer or proofreader, and say what support they may need (blindness, low
vision and so on). The support details are private to the person and the library's managers.
Managers see it all in Desk → Reader Profiles and can give a volunteer the role.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

MANAGERS = ("System Manager", "SOK Super Admin", "ResDesk Manager")
ROLES = ("ResDesk Proofreader", "ResDesk Cataloguer")
FIELDS = (
	"kind",
	"organisation",
	"role_title",
	"country",
	"website",
	"about",
	"show_publicly",
	"wants_reviewer",
	"wants_proofreader",
	"volunteer_note",
	"access_need",
	"access_note",
)
FLAGS = ("show_publicly", "wants_reviewer", "wants_proofreader")
LIMITS = {
	"organisation": 140,
	"role_title": 140,
	"country": 80,
	"website": 200,
	"about": 1500,
	"volunteer_note": 600,
	"access_note": 600,
}


def _signed_in() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in first."), frappe.PermissionError)
	return frappe.session.user


def has_profile(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user != "Guest" and bool(frappe.db.exists("RD Reader Profile", user))


@frappe.whitelist()
def mine() -> dict:
	user = _signed_in()
	row = (
		frappe.db.get_value("RD Reader Profile", user, list(FIELDS), as_dict=True)
		if has_profile(user)
		else {}
	)
	options = frappe.get_meta("RD Reader Profile").get_field("access_need").options.split("\n")
	return {
		"exists": bool(row),
		"profile": row or {},
		"access_options": options,
		"name": frappe.db.get_value("User", user, "full_name"),
	}


def clean(values: dict) -> dict:
	"""Only the known fields, trimmed to a sensible length; the tick boxes as 0 or 1."""
	out = {}
	for key in FIELDS:
		if key not in values:
			continue
		v = values[key]
		out[key] = cint(v) if key in FLAGS else (str(v or "").strip()[: LIMITS.get(key, 140)])
	if out.get("kind") not in (None, "Individual", "Organisation"):
		out["kind"] = "Individual"
	site = out.get("website")
	if site and not site.lower().startswith(("http://", "https://")):
		out["website"] = "https://" + site
	return out


@frappe.whitelist()
def save(**values) -> dict:
	user = _signed_in()
	data = clean(values)
	before = {k: 0 for k in ("wants_reviewer", "wants_proofreader")}
	if frappe.db.exists("RD Reader Profile", user):
		doc = frappe.get_doc("RD Reader Profile", user)
		before = {k: cint(doc.get(k)) for k in before}
		doc.update(data)
	else:
		doc = frappe.get_doc({"doctype": "RD Reader Profile", "user": user, **data})
	doc.flags.ignore_permissions = True
	doc.save() if doc.get("creation") else doc.insert()
	if any(cint(data.get(k)) and not before[k] for k in before):
		_tell_managers(doc)
	frappe.db.commit()
	return {"saved": True}


def _tell_managers(doc) -> None:
	"""A Desk notification to managers when someone newly offers to help."""
	from sok_resdesk.access import MANAGER_ROLES

	people = {
		u
		for u in frappe.get_all(
			"Has Role", filters={"role": ("in", MANAGER_ROLES), "parenttype": "User"}, pluck="parent"
		)
		if u not in ("Guest",) and frappe.db.get_value("User", u, "enabled")
	}
	for u in people:
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": u,
					"type": "Alert",
					"subject": _("{0} offers to help as a reviewer or proofreader").format(
						doc.full_name or doc.user
					),
					"document_type": "RD Reader Profile",
					"document_name": doc.name,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error("Research Desk: volunteer notice")


@frappe.whitelist()
def grant(user: str, role: str) -> dict:
	"""Managers: give a volunteer the proofreader or cataloguer role."""
	frappe.only_for(MANAGERS)
	if role not in ROLES:
		frappe.throw(_("Choose proofreader or cataloguer."))
	doc = frappe.get_doc("User", user)
	if role not in {r.role for r in doc.roles}:
		doc.append("roles", {"role": role})
		doc.flags.ignore_permissions = True
		doc.save()
	return {"message": _("{0} now has the {1} role.").format(doc.full_name or user, role)}
