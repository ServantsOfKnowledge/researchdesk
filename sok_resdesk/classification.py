"""Governance Mode: setting a record's level and department, and keeping the rules that go with it.

A classified or department-scoped record has one line in RD Item Scope (its level and department;
apart from the item because the item's own table is already full) and carries the visibility
"Cleared only", which the plain access rules never show to anyone (core/access.py); the people
cleared for it see it through access.effective. The level and department are indexed beside the
visibility, so search honours them. Clearances, departments and every change of classification are
written to the audit log.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import access, audit, clearance
from sok_resdesk.core import classification as levels
from sok_resdesk.core.access import CLEARED_ONLY, LOGIN_TO_FIND

CLASSIFIERS = ("ResDesk Security Officer", "SOK Super Admin", "ResDesk Manager")
SCOPE = "RD Item Scope"


def classified_mode() -> bool:
	from sok_resdesk import classified

	return classified.on()


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
	rank, departments = clearance.clearance()
	if levels.rank(level) > rank or (
		department and departments is not None and department not in departments
	):
		frappe.throw(_("You cannot classify a record above your own clearance."), frappe.PermissionError)


def _reindex(names: list[str]) -> None:
	from sok_resdesk.outbound import reconcile_soon
	from sok_resdesk.search import update_item_fields

	reconcile_soon()  # a classified book leaves the public mirror

	if len(names) <= access.BACKGROUND_OVER:
		update_item_fields(names, wait=True)  # hidden from search before this returns
	else:
		frappe.enqueue(update_item_fields, names=names, queue="long", timeout=3600)


# -- one record: the RD Item Scope form -------------------------------------------------------


def on_scope_validate(doc) -> None:
	if not access.governed():
		frappe.throw(_("Switch on Governance Mode (Settings) before classifying records."))
	doc.class_rank = levels.rank(doc.classification)
	if not doc.class_rank and not doc.department:
		frappe.throw(_("An Unclassified record with no department needs no line here: delete it instead."))
	_may_classify(doc.classification, doc.department)
	old = doc.get_doc_before_save()
	if old:  # no one reclassifies what they are not cleared for
		_may_classify(old.classification, old.department)
		if (old.department or "") != (doc.department or ""):
			_not_held([doc.item])
	_not_below_files([doc.item], doc.class_rank, doc.department)
	if not doc.visibility_before:
		current = frappe.db.get_value("RD Item", doc.item, "visibility")
		doc.visibility_before = current if current != CLEARED_ONLY else LOGIN_TO_FIND


def apply_to_item(item: str) -> None:
	"""After the scope is saved: the record becomes Cleared only, at once in search too."""
	frappe.db.set_value("RD Item", item, "visibility", CLEARED_ONLY, update_modified=False)
	frappe.db.delete("RD Review Flag", {"item": item})  # a classified record is not in the review queue
	level, department = frappe.db.get_value(SCOPE, item, ["classification", "department"])
	audit.record("classification", item, f"{level} {department or ''}".strip())
	_reindex([item])


def _not_below_files(names: list[str], rank: int, department: str | None) -> None:
	"""A record cannot be classified above the file it is filed in: raise the file first."""
	from sok_resdesk.register import files_below

	if rank or department:
		n = files_below(names, rank, department)
		if n:
			frappe.throw(
				_(
					"{0} files hold this record at a lower level or in another office: raise those files first (File Register)."
				).format(n)
			)


def _not_held(names: list[str]) -> None:
	"""A legal hold can follow a record's department, so the department is not changed under it."""
	from sok_resdesk.retention import held

	under = held(names)
	if under:
		frappe.throw(_("{0} is under a legal hold: release the hold first.").format(", ".join(sorted(under))))


def release_item(doc) -> None:
	"""The scope line is deleted: the record has the visibility it had before."""
	_not_held([doc.item])
	if frappe.db.get_value("RD Item", doc.item, "visibility") == CLEARED_ONLY:
		frappe.db.set_value(
			"RD Item", doc.item, "visibility", doc.visibility_before or LOGIN_TO_FIND, update_modified=False
		)
	audit.record("classification", doc.item, "declassified")
	_reindex([doc.item])


# -- many records: Items list → Actions → Set Classification -----------------------------------


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
	from sok_resdesk.retention import held

	selected = access.select_items(names=names, filters=filters)
	under_hold = held(selected)  # a held record keeps its department and level until the hold is released
	selected = [n for n in selected if n not in under_hold]
	rank = levels.rank(level)
	_not_below_files(selected, rank, department)
	user, now = frappe.session.user, now_datetime()
	for i in range(0, len(selected), 500):
		chunk = tuple(selected[i : i + 500])
		if rank or department:
			frappe.db.sql(
				f"""insert into `tab{SCOPE}`
				(name, creation, modified, modified_by, owner, docstatus, idx, item, classification, class_rank,
				department, visibility_before)
				select name, %(now)s, %(now)s, %(user)s, %(user)s, 0, 0, name, %(level)s, %(rank)s, %(dept)s,
					if(ifnull(visibility, '') in ('', %(c)s), %(find)s, visibility)
				from `tabRD Item` where name in %(names)s
				on duplicate key update classification = values(classification),
					class_rank = values(class_rank), department = values(department), modified = values(modified)""",
				{
					"now": now,
					"user": user,
					"level": level,
					"rank": rank,
					"dept": department or None,
					"c": CLEARED_ONLY,
					"find": LOGIN_TO_FIND,
					"names": chunk,
				},
			)
			frappe.db.sql("update `tabRD Item` set visibility = %s where name in %s", (CLEARED_ONLY, chunk))
		else:  # declassify: back to what each had before, and no scope line
			frappe.db.sql(
				f"""update `tabRD Item` i join `tab{SCOPE}` s on s.name = i.name
				set i.visibility = if(ifnull(s.visibility_before, '') = '', %s, s.visibility_before)
				where i.name in %s and i.visibility = %s""",
				(LOGIN_TO_FIND, chunk, CLEARED_ONLY),
			)
			frappe.db.sql(f"delete from `tab{SCOPE}` where name in %s", (chunk,))
	frappe.db.commit()
	audit.record("classification", detail=f"{len(selected)} records → {level} {department}".strip())
	_reindex(selected)
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
	from sok_resdesk import classified

	classified.enforce(doc)  # classified mode keeps Governance Mode and its limits on
	if cint(doc.get("governance")):
		return
	was = frappe.db.get_single_value("RD Settings", "governance")
	if cint(was) and frappe.db.exists("RD Item", {"visibility": CLEARED_ONLY}):
		frappe.throw(
			_("Governance Mode cannot be switched off while classified records exist. Declassify them first.")
		)
