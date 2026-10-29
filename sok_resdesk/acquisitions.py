"""Acquisitions: vendors, purchase orders, and receiving books into the library's copies.

An order is written as a draft, placed (*Ordered*), and received in one or several deliveries. Receiving
makes one RD Copy per book that arrived, each with its own barcode, on the shelf ready to lend; a book the
catalogue does not know yet gets a catalogue record (source *Other*) from the order line.
"""

from __future__ import annotations

import hashlib

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from sok_resdesk import access, features
from sok_resdesk.core import budget as money
from sok_resdesk.lending import STAFF

MAX_PER_DELIVERY = 500


def _staff() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for(STAFF)


def status_of(lines) -> str:
	"""Part Received or Received, from what each line ordered and has received."""
	ordered = sum(cint(r.quantity) for r in lines)
	got = sum(min(cint(r.received), cint(r.quantity)) for r in lines)
	if ordered and got >= ordered:
		return "Received"
	return "Part Received" if got else "Ordered"


def _record_for(line, order: str) -> str:
	"""The catalogue record a line's copies belong to: the one chosen, or one made from the line."""
	if line.item and frappe.db.exists("RD Item", line.item):
		return line.item
	from sok_resdesk.catalogue import upsert_item

	key = hashlib.sha1(f"{order}|{line.idx}|{line.title}".encode()).hexdigest()[:10]
	name, _created = upsert_item(
		{
			"item_id": f"acq-{key}",
			"source": "Other",
			"title": line.title,
			"creators": [line.author] if line.author else [],
			"isbn": line.isbn or "",
			"item_type": "Book",
		}
	)
	line.item = name
	return name


@frappe.whitelist(methods=["POST"])
def place(order: str) -> dict:
	_staff()
	doc = frappe.get_doc("RD Purchase Order", order)
	if doc.status != "Draft":
		frappe.throw(_("Only a draft order can be placed."))
	if not doc.lines:
		frappe.throw(_("Add the books to order first."))
	if doc.budget and not _fits(doc.budget, doc.total, exclude=doc.name):
		frappe.throw(
			_("This order is more than what is left in {0}. Raise the budget or order less.").format(
				doc.budget
			),
			title=_("Over budget"),
		)
	doc.status = "Ordered"
	doc.order_date = doc.order_date or nowdate()
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def cancel(order: str) -> dict:
	_staff()
	doc = frappe.get_doc("RD Purchase Order", order)
	if doc.status not in ("Draft", "Ordered"):
		frappe.throw(_("An order that has started to arrive cannot be cancelled."))
	doc.status = "Cancelled"
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def receive(order: str, quantities=None, location: str = "") -> dict:
	"""Books arrived: `quantities` is a JSON object {line number: how many came} (empty: everything still
	outstanding). Makes the copies and returns their barcodes, to print as labels."""
	_staff()
	frappe.db.get_value(
		"RD Purchase Order", order, "name", for_update=True
	)  # two deliveries entered together must not make the copies twice
	doc = frappe.get_doc("RD Purchase Order", order)
	if doc.status not in ("Ordered", "Part Received"):
		frappe.throw(_("Place the order before receiving books."))
	wanted = (
		frappe.parse_json(quantities) if isinstance(quantities, str) and quantities else (quantities or {})
	)
	if not isinstance(wanted, dict):
		frappe.throw(_("Give the quantities as {line number: how many}."))
	made, total = [], 0
	for line in doc.lines:
		outstanding = max(cint(line.quantity) - cint(line.received), 0)
		qty = outstanding if not wanted else min(cint(wanted.get(str(line.idx))), outstanding)
		if qty <= 0:
			continue
		total += qty
		if total > MAX_PER_DELIVERY:
			frappe.throw(_("Receive at most {0} books at a time.").format(MAX_PER_DELIVERY))
		item = _record_for(line, doc.name)
		for _i in range(qty):
			copy = frappe.get_doc(
				{
					"doctype": "RD Copy",
					"item": item,
					"status": "Available",
					"price": flt(line.unit_price),
					"acquired_on": nowdate(),
					"order": doc.name,
					"location": location or "",
				}
			)
			copy.insert(ignore_permissions=True)
			made.append({"barcode": copy.name, "title": line.title})
		line.received = cint(line.received) + qty
	if not made:
		frappe.throw(_("Nothing to receive."))
	doc.status = status_of(doc.lines)
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status, "copies": made, "message": _("{0} copies added.").format(len(made))}


@frappe.whitelist()
def labels(barcodes: str) -> dict:
	"""Barcode labels (SVG) for copies, to print and stick on the books."""
	_staff()
	from sok_resdesk.core.barcode import svg

	out = []
	for code in [c.strip().upper() for c in (barcodes or "").split(",") if c.strip()][:500]:
		title = frappe.db.get_value("RD Copy", code, "item_title")
		if title is not None or frappe.db.exists("RD Copy", code):
			out.append({"barcode": code, "title": title or "", "svg": svg(code, height=40, module=2)})
	return {"labels": out}


# -- budgets and invoices ----------------------------------------------------------------------------


def _managers() -> None:
	"""Money decisions (approving and paying an invoice, a budget) are a manager's."""
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for(access.MANAGER_ROLES)


def _budget_figures(budget: str, exclude: str = "") -> tuple[float, list, float]:
	"""(amount, [(order total, status, invoiced on it)], invoiced on the budget) for the arithmetic."""
	amount = flt(frappe.db.get_value("RD Budget", budget, "amount"))
	orders = []
	for po in frappe.get_all(
		"RD Purchase Order",
		filters={"budget": budget, "name": ("!=", exclude)},
		fields=["name", "total", "status"],
	):
		invoiced = flt(
			frappe.db.sql(
				"select coalesce(sum(amount), 0) from `tabRD Invoice` where `order`=%s and status!='Cancelled'",
				po.name,
			)[0][0]
		)
		orders.append((flt(po.total), po.status, invoiced))
	spent = flt(
		frappe.db.sql(
			"select coalesce(sum(amount), 0) from `tabRD Invoice` where budget=%s and status!='Cancelled'",
			budget,
		)[0][0]
	)
	return amount, orders, spent


def _fits(budget: str, extra: float, exclude: str = "") -> bool:
	return money.fits(*_budget_figures(budget, exclude), extra)


@frappe.whitelist()
def budget_summary(budget: str) -> dict:
	"""What a budget holds: its amount, what orders have committed, what invoices have spent, what is left."""
	_staff()
	return money.summary(*_budget_figures(budget))


def _received_value(order: str) -> float:
	return money.received_value(
		[(r.received, r.unit_price) for r in frappe.get_doc("RD Purchase Order", order).lines]
	)


def check_invoice(doc) -> None:
	"""RD Invoice.validate: the order's vendor and budget, a number not used before, and the three-way check."""
	if flt(doc.amount) <= 0:
		frappe.throw(_("The invoice amount must be more than nothing."))
	doc.invoice_number = (doc.invoice_number or "").strip().upper()  # INV-1 and inv-1 are one invoice
	if doc.is_new():
		doc.status, doc.approved_by, doc.paid_on = "Draft", None, None  # only the buttons approve and pay
	else:
		before = doc.get_doc_before_save()
		if before and not doc.flags.get("from_workflow"):
			if doc.status != before.status or doc.approved_by != before.approved_by:
				frappe.throw(_("Use Approve, Record Payment or Cancel to change an invoice's state."))
			if before.status != "Draft" and any(
				doc.get(f) != before.get(f) for f in ("amount", "vendor", "order", "budget", "invoice_number")
			):
				frappe.throw(
					_("An invoice that has been approved cannot be changed. Cancel it and enter another.")
				)
	if frappe.db.exists(
		"RD Invoice",
		{
			"vendor": doc.vendor,
			"invoice_number": doc.invoice_number,
			"name": ("!=", doc.name),
			"status": ("!=", "Cancelled"),
		},
	):
		frappe.throw(_("This vendor's invoice {0} is already entered.").format(doc.invoice_number))
	doc.match = ""
	if doc.order:
		po = frappe.get_doc("RD Purchase Order", doc.order)
		if po.vendor != doc.vendor:
			frappe.throw(_("The order {0} is with another vendor.").format(doc.order))
		doc.budget = doc.budget or po.budget
		doc.match = money.three_way(doc.amount, po.total, _received_value(doc.order))


def _invoice(name: str, *states: str):
	doc = frappe.get_doc("RD Invoice", name)
	if doc.status not in states:
		frappe.throw(_("An invoice that is {0} cannot be changed this way.").format(_(doc.status)))
	return doc


@frappe.whitelist(methods=["POST"])
def invoice_approve(invoice: str) -> dict:
	"""A manager approves an invoice for payment. One that asks for more than the order or the books received
	is approved only by someone who knows why, so it says so."""
	_managers()
	doc = _invoice(invoice, "Draft")
	if (
		cint(frappe.db.get_single_value("RD Settings", "invoice_separate_approval"))
		and doc.owner == frappe.session.user
	):
		frappe.throw(_("Another manager must approve an invoice you entered."))
	if doc.budget and not _fits(doc.budget, 0):
		frappe.throw(_("{0} is already over budget.").format(doc.budget), title=_("Over budget"))
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.flags.from_workflow = True
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status, "match": doc.match}


@frappe.whitelist(methods=["POST"])
def invoice_pay(invoice: str, note: str = "") -> dict:
	"""The library paid it (outside Research Desk): record how and when."""
	_managers()
	doc = _invoice(invoice, "Approved")
	doc.status = "Paid"
	doc.paid_on = nowdate()
	doc.payment_note = note or doc.payment_note
	doc.flags.from_workflow = True
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def invoice_cancel(invoice: str) -> dict:
	_managers()
	doc = _invoice(invoice, "Draft", "Approved")
	doc.status = "Cancelled"
	doc.flags.from_workflow = True
	doc.flags.ignore_permissions = True
	doc.save()
	return {"status": doc.status}
