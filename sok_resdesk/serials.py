"""Periodicals: a subscription lists the issues it expects, staff check each in when it arrives, and an issue
that does not come is marked Late (and managers are told in the Desk, not by email) so it can be claimed.

A subscription belongs to a catalogue record for the periodical; each received issue can become a copy of
it (reference only: a current issue is read in the library) with a barcode like any other copy.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, nowdate

from sok_resdesk import access, features
from sok_resdesk.core import serials as rules
from sok_resdesk.lending import STAFF

MAX_AT_ONCE = 60


def _staff() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for(STAFF)


def _subscription(name: str):
	doc = frappe.get_doc("RD Serial Subscription", name)
	if doc.status != "Active":
		frappe.throw(_("This subscription is {0}.").format(_(doc.status)))
	return doc


@frappe.whitelist(methods=["POST"])
def generate(subscription: str, count: int = 12) -> dict:
	"""Make the next `count` expected issues, after the last one there is (or from the first date)."""
	_staff()
	sub = _subscription(subscription)
	count = max(1, min(cint(count), MAX_AT_ONCE))
	last = frappe.db.get_value(
		"RD Serial Issue", {"subscription": sub.name}, "expected_on", order_by="expected_on desc"
	)
	if last:
		first = rules.step(getdate(last), sub.frequency)
	elif sub.first_issue_due:
		first = getdate(sub.first_issue_due)
	else:
		frappe.throw(_("Give the date the first issue is due."))
	made = 0
	for day in rules.expected_dates(first, sub.frequency, count):
		if sub.ends_on and day > getdate(sub.ends_on):
			break
		frappe.get_doc(
			{
				"doctype": "RD Serial Issue",
				"subscription": sub.name,
				"label": rules.label(day, sub.frequency),
				"expected_on": day,
				"status": "Expected",
			}
		).insert(ignore_permissions=True)
		made += 1
	if not made:
		frappe.throw(_("The subscription ends before another issue is due."))
	return {"made": made, "message": _("{0} issues expected.").format(made)}


def _catalogue_record(sub) -> str:
	"""The periodical's catalogue record: the one chosen, or one made now from the subscription."""
	if sub.item and frappe.db.exists("RD Item", sub.item):
		return sub.item
	import hashlib

	from sok_resdesk.catalogue import upsert_item

	name, _created = upsert_item(
		{
			"item_id": "ser-" + hashlib.sha1(sub.name.encode()).hexdigest()[:10],
			"source": "Other",
			"title": sub.title,
			"creators": [],
			"item_type": "Periodical",
		}
	)
	frappe.db.set_value("RD Serial Subscription", sub.name, "item", name)
	return name


@frappe.whitelist(methods=["POST"])
def receive(issue: str, make_copy: int = 1) -> dict:
	"""An issue arrived: check it in, and (by default) shelve it as a reference copy with a barcode."""
	_staff()
	row = frappe.get_doc("RD Serial Issue", issue)
	if row.status == "Received":
		frappe.throw(_("This issue is already checked in."))
	sub = frappe.get_doc("RD Serial Subscription", row.subscription)
	row.status = "Received"
	row.received_on = nowdate()
	barcode = ""
	if cint(make_copy):
		copy = frappe.get_doc(
			{
				"doctype": "RD Copy",
				"item": _catalogue_record(sub),
				"status": "Available",
				"reference_only": 1,
				"call_number": row.label,
				"location": sub.location or "",
				"acquired_on": nowdate(),
				"notes": f"{sub.title}, {row.label}",
			}
		)
		copy.insert(ignore_permissions=True)
		barcode = copy.name
		row.copy = barcode
	row.flags.ignore_permissions = True
	row.save()
	return {
		"status": row.status,
		"barcode": barcode,
		"message": _("{0}, {1}: checked in.").format(sub.title, row.label),
	}


@frappe.whitelist(methods=["POST"])
def claim(issue: str) -> dict:
	"""The library has asked the vendor for a missing issue (outside Research Desk): note that it did."""
	_staff()
	row = frappe.get_doc("RD Serial Issue", issue)
	if row.status not in ("Expected", "Late"):
		frappe.throw(_("Only an issue that has not come can be claimed."))
	row.status = "Claimed"
	row.claimed_on = nowdate()
	row.flags.ignore_permissions = True
	row.save()
	return {"status": row.status}


@frappe.whitelist(methods=["POST"])
def mark_missing(issue: str) -> dict:
	_staff()
	row = frappe.get_doc("RD Serial Issue", issue)
	if row.status in ("Received", "Missing"):
		frappe.throw(_("This issue is already settled."))
	row.status = "Missing"
	row.flags.ignore_permissions = True
	row.save()
	return {"status": row.status}


@features.scheduled("lending")
def daily() -> None:
	"""Issues that are overdue become Late, and managers get one Desk alert for the lot (no email)."""
	today = getdate(nowdate())
	late = []
	for issue in frappe.get_all(
		"RD Serial Issue",
		filters={"status": "Expected", "expected_on": ("<", add_days(today, -1))},
		fields=["name", "subscription", "label", "expected_on"],
	):
		days = frappe.db.get_value(
			"RD Serial Subscription", issue.subscription, ["claim_after_days", "status"], as_dict=True
		)
		if (
			days
			and days.status == "Active"
			and rules.is_late(getdate(issue.expected_on), today, days.claim_after_days)
		):
			frappe.db.set_value("RD Serial Issue", issue.name, "status", "Late")
			late.append(issue)
	if late:
		_tell_managers(late)
	frappe.db.commit()


def _tell_managers(late: list) -> None:
	managers = {
		u
		for u in frappe.get_all(
			"Has Role", filters={"role": ("in", access.MANAGER_ROLES), "parenttype": "User"}, pluck="parent"
		)
		if u != "Guest" and frappe.db.get_value("User", u, "enabled")
	}
	subject = _("{0} periodical issues are late: claim them from the vendors.").format(len(late))
	for user in managers:
		try:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"document_type": "RD Serial Issue",
					"document_name": late[0].name,
					"subject": subject,
				}
			).insert(ignore_permissions=True)
		except Exception:  # an alert that fails must not stop the nightly job
			frappe.log_error(title="Research Desk: could not alert a manager about late issues")
