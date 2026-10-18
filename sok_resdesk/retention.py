"""Retention rules, legal holds and disposal (docs/governance.md#retention-and-legal-holds).

A rule says how long records are kept. Each day the due ones are listed in a Disposal (a draft);
a records officer approves it; only then is anything done. A record under an active legal hold is
never listed, never disposed of and cannot be deleted by anyone, however it is asked.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from sok_resdesk import audit
from sok_resdesk.core import classification as levels
from sok_resdesk.core import retention as rules

OFFICER = "ResDesk Records Officer"
APPROVERS = (OFFICER, "SOK Super Admin")
MAX_LISTED = 2000  # one disposal stays something a person can review
SCOPE = "RD Item Scope"


def _parents() -> dict[str, str]:
	return dict(
		frappe.db.sql(
			"select name, parent_department from `tabRD Department` where ifnull(parent_department, '') != ''"
		)
	)


def _under(department: str) -> set[str]:
	return levels.expand([department], _parents())


# -- legal holds ------------------------------------------------------------------------------


def held(names: list[str]) -> set[str]:
	"""Those of `names` that are under an active legal hold."""
	names = [n for n in dict.fromkeys(names) if n]
	if not names:
		return set()
	found = set(
		frappe.db.sql_list(
			"""select distinct i.item from `tabRD Legal Hold Item` i join `tabRD Legal Hold` h on h.name = i.parent
			where h.status = 'Active' and i.item in %s""",
			(tuple(names),),
		)
	)
	offices: set[str] = set()
	for dept in frappe.get_all(
		"RD Legal Hold", filters={"status": "Active", "department": ("!=", "")}, pluck="department"
	):
		offices |= _under(dept)
	if offices:
		found |= set(
			frappe.db.sql_list(
				f"select item from `tab{SCOPE}` where item in %s and department in %s",
				(tuple(names), tuple(offices)),
			)
		)
	return found


def on_item_trash(doc, method=None) -> None:
	"""RD Item on_trash, before anything else: a record under a hold is not deleted."""
	if held([doc.name]):
		frappe.throw(_("{0} is under a legal hold and cannot be deleted.").format(doc.name))


def on_hold_validate(doc, method=None) -> None:
	if not (doc.items or doc.department):
		frappe.throw(_("A hold needs records, a department, or both."))
	if doc.department and not frappe.db.exists("RD Department", doc.department):
		frappe.throw(_("Unknown department: {0}").format(doc.department))
	old = doc.get_doc_before_save()
	if doc.is_new():
		doc.placed_by, doc.placed_on = frappe.session.user, now_datetime()
		doc.released_by = doc.released_on = None
		return
	if old.status == "Released":
		frappe.throw(_("A released hold cannot be changed. Place a new one."))
	# who placed it, and when, is not for editing
	doc.placed_by, doc.placed_on = old.placed_by, old.placed_on
	doc.released_by, doc.released_on = old.released_by, old.released_on
	if doc.status == "Released":
		doc.released_by, doc.released_on = frappe.session.user, now_datetime()


def on_hold_change(doc, method=None) -> None:
	old = doc.get_doc_before_save()
	dropped = sorted({r.item for r in old.items or []} - {r.item for r in doc.items or []}) if old else []
	audit.record(
		"legal_hold",
		detail=f"{doc.name} {doc.status}: {len(doc.items or [])} records"
		+ (f", department {doc.department}" if doc.department else "")
		+ (f"; no longer held: {', '.join(dropped[:20])}" if dropped else ""),
	)


# -- the daily list ---------------------------------------------------------------------------


def _matches(rule) -> list[dict]:
	"""Records a rule covers, with what is needed to date them."""
	where, values = ["1=1"], {}
	if rule.department:
		where.append("s.department in %(offices)s")
		values["offices"] = tuple(_under(rule.department)) or ("",)
	if rule.collection:
		where.append(
			"i.name in (select parent from `tabRD Item Collection` where collection = %(collection)s)"
		)
		values["collection"] = rule.collection
	return frappe.db.sql(
		f"""select i.name, i.year, i.creation, ifnull(s.department, '') as department,
		ifnull(s.classification, 'Unclassified') as level
		from `tabRD Item` i left join `tab{SCOPE}` s on s.item = i.name where {" and ".join(where)}""",
		values,
		as_dict=True,
	)


def due_records() -> dict[str, dict]:
	"""{rule: {item: row}} of what is due today, each record under the one rule that governs it.
	A record that any matching rule cannot date (no year, or a year no date can hold) is left alone,
	so a longer rule that cannot be worked out is never overridden by a shorter one."""
	today = getdate(nowdate())
	candidates: dict[str, list] = {}
	undatable: set[str] = set()
	rows: dict[str, dict] = {}
	for rule in frappe.get_all(
		"RD Retention Rule",
		filters={"enabled": 1},
		fields=["name", "years", "basis", "action", "department", "collection"],
	):
		for r in _matches(frappe._dict(rule)):
			due = rules.due_on(rule.basis, rule.years, r.year, getdate(r.creation))
			if due:
				candidates.setdefault(r.name, []).append((rule.name, due, rule.action))
				rows[r.name] = r
			else:
				undatable.add(r.name)
	out: dict[str, dict] = {}
	for item, options in candidates.items():
		if item in undatable:
			continue
		rule, due, _action = rules.governing(options)
		if due <= today:
			out.setdefault(rule, {})[item] = {**rows[item], "due": due}
	return out


def prepare() -> int:
	"""Daily: a draft Disposal for each rule with records due (not while one is open). Returns the count."""
	frappe.flags.rd_retention = True
	made = 0
	for rule, items in due_records().items():
		if frappe.db.exists("RD Disposal", {"rule": rule, "status": ("in", ("Draft", "Approved"))}):
			continue
		# not again: what is listed, disposed of or transferred, and what was kept in the last 30 days
		already = set(
			frappe.db.sql_list(
				"""select i.item from `tabRD Disposal Item` i join `tabRD Disposal` d on d.name = i.parent
				where d.status != 'Cancelled' and (i.outcome in ('Pending', 'Disposed', 'Transferred')
				or (i.outcome = 'Kept' and d.done_on > date_sub(now(), interval 30 day)))"""
			)
		)
		names = [n for n in items if n not in already]
		under_hold = held(names)
		names = [n for n in names if n not in under_hold][:MAX_LISTED]
		if not names:
			continue
		frappe.get_doc(
			{
				"doctype": "RD Disposal",
				"rule": rule,
				"action": frappe.db.get_value("RD Retention Rule", rule, "action"),
				"status": "Draft",
				"prepared_on": now_datetime(),
				"items": [{"item": n, "due_on": items[n]["due"]} for n in names],
			}
		).insert(ignore_permissions=True)
		made += 1
	frappe.db.commit()
	return made


# -- approval and disposal -------------------------------------------------------------------------


def _only_officers() -> None:
	if frappe.session.user != "Administrator":
		frappe.only_for(APPROVERS)


def _lock_draft(disposal: str) -> None:
	"""Under a row lock, so two clicks (or a click and a cancel) cannot both win."""
	row = frappe.db.sql("select status from `tabRD Disposal` where name=%s for update", disposal)
	if not row or row[0][0] != "Draft":
		frappe.db.rollback()
		frappe.throw(_("Only a draft can be approved or cancelled."))


@frappe.whitelist(methods=["POST"])
def approve(disposal: str) -> None:
	"""The records officer approves a draft: the records on it are then disposed of in the background."""
	_only_officers()
	_lock_draft(disposal)
	frappe.flags.rd_retention = True
	doc = frappe.get_doc("RD Disposal", disposal)
	doc.status, doc.approved_by = "Approved", frappe.session.user
	doc.save(ignore_permissions=True)
	audit.record("disposal", detail=f"{doc.name} approved: {len(doc.items)} records, {doc.action}")
	frappe.enqueue(
		"sok_resdesk.retention.execute",
		queue="long",
		timeout=3600,
		disposal=doc.name,
		enqueue_after_commit=True,
	)


@frappe.whitelist(methods=["POST"])
def cancel(disposal: str) -> None:
	"""A draft is cancelled; an approved or finished Disposal is the record of what was done."""
	_only_officers()
	_lock_draft(disposal)
	frappe.flags.rd_retention = True
	doc = frappe.get_doc("RD Disposal", disposal)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	audit.record("disposal", detail=f"{doc.name} cancelled by {frappe.session.user}")


def execute(disposal: str) -> None:
	"""Background. Every record is checked again just before it is dealt with, against the live data:
	still due under an enabled rule, not under a hold (one placed since the list was made wins), and
	within what the approver is cleared for (a record they cannot see is left for an officer who can)."""
	from sok_resdesk import access

	frappe.flags.rd_retention = True
	doc = frappe.get_doc("RD Disposal", disposal)
	if doc.status != "Approved":
		return
	still_due = due_records().get(doc.rule, {})
	done = {"Disposed": 0, "Transferred": 0, "Kept": 0}
	try:
		for n, row in enumerate([r for r in doc.items if r.outcome == "Pending"], 1):
			rank, department = access.scope_of(row.item)
			if held([row.item]):
				row.outcome, row.why = "Kept", "legal hold"
			elif row.item not in still_due:
				row.outcome, row.why = "Kept", "no longer due"
			elif not access.is_cleared(rank, department, doc.approved_by):
				row.outcome, row.why = "Kept", "needs an officer cleared for it"
			elif doc.action == "Destroy":
				try:
					if frappe.db.exists("RD Item", row.item):
						frappe.db.delete(SCOPE, {"item": row.item})
						frappe.delete_doc("RD Item", row.item, force=True, ignore_permissions=True)
						row.outcome = "Disposed"
					else:
						row.outcome, row.why = "Kept", "already gone"
				except Exception as e:  # a hold placed this very moment, or a record that cannot be deleted
					frappe.db.rollback()
					row.outcome, row.why = "Kept", str(e)[:120]
			elif doc.action == "Transfer to archives":
				row.outcome = "Transferred"
			else:
				row.outcome, row.why = "Kept", "reviewed"
			done[row.outcome] += 1
			if n % 100 == 0:
				doc.save(ignore_permissions=True)
				frappe.db.commit()
	finally:  # what was done is recorded even if the run stops half way
		doc.status = "Done" if all(r.outcome != "Pending" for r in doc.items) else "Approved"
		doc.done_on = now_datetime()
		doc.certificate = (
			f"{done['Disposed']} records destroyed, {done['Transferred']} listed for transfer to the archives, "
			f"{done['Kept']} kept, under rule {doc.rule}, approved by {doc.approved_by}. "
			"The catalogue record is removed; files in the library's storage are not erased by Research Desk."
		)
		doc.save(ignore_permissions=True)
		audit.record("disposal", detail=f"{doc.name} {doc.status}: {doc.certificate[:180]}")
		frappe.db.commit()
