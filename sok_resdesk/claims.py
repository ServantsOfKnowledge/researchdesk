"""Claims to vendors: the orders and periodical issues a vendor owes, a letter to ask for them, and a note that
it was sent. Research Desk writes the letter; the library sends it (no email goes from here).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from sok_resdesk import features
from sok_resdesk.core import claims as rules
from sok_resdesk.lending import STAFF


def _staff() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for(STAFF)


def _owed(vendor: str) -> tuple[list, list]:
	"""(orders, issues) this vendor owes and that are due for a claim."""
	today = getdate(nowdate())
	orders = []
	for po in frappe.get_all(
		"RD Purchase Order",
		filters={"vendor": vendor, "status": ("in", ("Ordered", "Part Received"))},
		fields=["name", "order_date", "expected_date", "claimed_on"],
	):
		if not rules.due_for_claim(
			po.expected_date and getdate(po.expected_date), po.claimed_on and getdate(po.claimed_on), today
		):
			continue
		lines = [
			(r.title, cint(r.quantity) - cint(r.received))
			for r in frappe.get_all(
				"RD Order Line", filters={"parent": po.name}, fields=["title", "quantity", "received"]
			)
			if cint(r.quantity) > cint(r.received)
		]
		orders.append({**po, "lines": lines})
	issues = []
	for sub in frappe.get_all(
		"RD Serial Subscription", filters={"vendor": vendor, "status": "Active"}, fields=["name", "title"]
	):
		for i in frappe.get_all(
			"RD Serial Issue",
			filters={"subscription": sub.name, "status": ("in", ("Late", "Claimed"))},
			fields=["name", "periodical", "label", "expected_on", "claimed_on", "status"],
		):
			if i.status == "Late" or rules.due_for_claim(
				getdate(i.expected_on), i.claimed_on and getdate(i.claimed_on), today
			):
				issues.append({**i, "title": i.periodical or sub.title})
	return orders, issues


@frappe.whitelist()
def letter(vendor: str) -> dict:
	"""The text of a claim letter for what this vendor owes (staff)."""
	_staff()
	orders, issues = _owed(vendor)
	if not (orders or issues):
		return {"orders": 0, "issues": 0, "text": ""}
	from sok_resdesk.catalogue import settings

	text = rules.letter(
		settings().portal_title or "",
		frappe.db.get_value("RD Vendor", vendor, "vendor_name") or vendor,
		orders,
		issues,
		getdate(nowdate()),
	)
	return {"orders": len(orders), "issues": len(issues), "text": text}


@frappe.whitelist(methods=["POST"])
def mark_claimed(vendor: str) -> dict:
	"""The library sent the claim: note the date on each order and issue so it is not claimed again at once."""
	_staff()
	orders, issues = _owed(vendor)
	for o in orders:
		frappe.db.set_value(
			"RD Purchase Order",
			o["name"],
			{
				"claimed_on": nowdate(),
				"claim_count": cint(frappe.db.get_value("RD Purchase Order", o["name"], "claim_count")) + 1,
			},
		)
	for i in issues:
		frappe.db.set_value("RD Serial Issue", i["name"], {"status": "Claimed", "claimed_on": nowdate()})
	return {"orders": len(orders), "issues": len(issues)}


@features.scheduled("lending")
def daily() -> None:
	"""Managers get one Desk alert for orders past their date that nobody has claimed (no email)."""
	from sok_resdesk.serials import alert_managers

	today = getdate(nowdate())
	overdue = [
		po
		for po in frappe.get_all(
			"RD Purchase Order",
			filters={"status": ("in", ("Ordered", "Part Received")), "expected_date": ("<", today)},
			fields=["name", "expected_date", "claimed_on"],
		)
		if rules.due_for_claim(getdate(po.expected_date), po.claimed_on and getdate(po.claimed_on), today)
	]
	if overdue:
		alert_managers(
			_("{0} orders are past their date: claim them from the vendors.").format(len(overdue)),
			"RD Purchase Order",
			overdue[0].name,
		)
	frappe.db.commit()
