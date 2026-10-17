"""Governance Mode: setting a record's level and department, and keeping the rules that go with it.

A classified or department-scoped record carries the visibility "Cleared only", which the plain
access rules never show to anyone (core/access.py); the people cleared for it see it through
access.effective. The level and department are indexed beside the visibility, so search honours
them. Clearances, departments and every change of classification are written to the audit log.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import access, audit
from sok_resdesk.core import classification as levels
from sok_resdesk.core.access import CLEARED_ONLY, LOGIN_TO_FIND

CLASSIFIERS = ("ResDesk Security Officer", "SOK Super Admin", "ResDesk Manager")


def classified_mode() -> bool:
	return bool(frappe.conf.get("resdesk_classified"))


def _may_classify(level: str, department: str | None) -> None:
	"""Only a security officer or manager classifies, and never above their own clearance."""
	if level not in levels.allowed_levels(classified_mode()):
		frappe.throw(
			_("{0} needs Classified mode, which this installation was not set up with.").format(level)
		)
	if frappe.session.user == "Administrator":
		return
	if not set(frappe.get_roles()) & set(CLASSIFIERS):
		frappe.throw(_("Only a security officer or a manager can classify records."), frappe.PermissionError)
	rank, departments = access.clearance()
	if levels.rank(level) > rank or (
		department and departments is not None and department not in departments
	):
		frappe.throw(_("You cannot classify a record above your own clearance."), frappe.PermissionError)


def on_item_validate(doc, method=None) -> None:
	"""Keeps the level number and the "Cleared only" visibility in step with the classification."""
	doc.class_rank = levels.rank(doc.classification)
	if not access.governed() and not doc.class_rank and not doc.department:
		return
	old = doc.get_doc_before_save()
	was = (old.classification or "Unclassified", old.department or "") if old else ("Unclassified", "")
	now = (doc.classification or "Unclassified", doc.department or "")
	if was != now:
		if not access.governed():
			frappe.throw(_("Switch on Governance Mode (Settings) before classifying records."))
		_may_classify(now[0], now[1])
		audit.record("classification", doc.name, f"{was[0]} {was[1]} → {now[0]} {now[1]}".strip())
	scoped = bool(doc.class_rank or doc.department)
	if scoped and doc.visibility != CLEARED_ONLY:
		doc.visibility_before = doc.visibility
		doc.visibility = CLEARED_ONLY
	elif not scoped and doc.visibility == CLEARED_ONLY:
		doc.visibility = doc.visibility_before or LOGIN_TO_FIND
		doc.visibility_before = ""


@frappe.whitelist(methods=["POST"])
def set_classification(level: str, department: str = "", names=None, filters=None) -> dict:
	"""Classify many records at once (Items list → Actions → Set Classification)."""
	frappe.only_for(CLASSIFIERS)
	if not access.governed():
		frappe.throw(_("Switch on Governance Mode (Settings) before classifying records."))
	if level not in levels.LEVELS:
		frappe.throw(_("Unknown level: {0}").format(level))
	if department and not frappe.db.exists("RD Department", department):
		frappe.throw(_("Unknown department: {0}").format(department))
	_may_classify(level, department)
	selected = access.select_items(names=names, filters=filters)
	rank, scoped = levels.rank(level), bool(levels.rank(level) or department)
	for i in range(0, len(selected), 500):
		frappe.db.sql(
			"""update `tabRD Item` set classification=%(level)s, class_rank=%(rank)s, department=%(dept)s,
			visibility_before = if(%(scoped)s and visibility != %(c)s, visibility, visibility_before),
			visibility = if(%(scoped)s, %(c)s,
				if(visibility = %(c)s, if(ifnull(visibility_before, '') = '', %(find)s, visibility_before), visibility))
			where name in %(names)s""",
			{
				"level": level,
				"rank": rank,
				"dept": department or None,
				"scoped": 1 if scoped else 0,
				"c": CLEARED_ONLY,
				"find": LOGIN_TO_FIND,
				"names": tuple(selected[i : i + 500]),
			},
		)
	frappe.db.commit()
	audit.record("classification", detail=f"{len(selected)} records → {level} {department}".strip())
	from sok_resdesk.search import update_item_fields

	if len(selected) <= access.BACKGROUND_OVER:
		update_item_fields(selected, wait=True)  # hidden from search before this returns
	else:
		frappe.enqueue(update_item_fields, names=selected, queue="long", timeout=3600)
	return {
		"count": len(selected),
		"message": _("{0} records are now {1}.").format(len(selected), _(level)),
	}


def on_clearance_change(doc, method=None) -> None:
	frappe.local.rd_clearance = {}
	removed = method == "on_trash"
	where = ", ".join(d.department for d in doc.departments or [])
	audit.record("clearance", doc.user, "removed" if removed else f"{doc.level}: {where or 'any department'}")


def check_governance_switch(doc, method=None) -> None:
	"""RD Settings: Governance Mode cannot be switched off while classified records exist, or their
	level and department would stop applying and they would be hidden from everyone."""
	if cint(doc.get("governance")):
		return
	was = frappe.db.get_single_value("RD Settings", "governance")
	if cint(was) and frappe.db.exists("RD Item", {"visibility": CLEARED_ONLY}):
		frappe.throw(
			_("Governance Mode cannot be switched off while classified records exist. Declassify them first.")
		)
