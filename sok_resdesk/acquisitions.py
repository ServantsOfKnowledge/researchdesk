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
from sok_resdesk.core import gst
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


LINE_FIELDS = ("description", "order_line", "hsn", "quantity", "rate", "gst_rate")
_SUPPLY = {"intra": "Within the state (CGST + SGST)", "inter": "Between states (IGST)"}


def _price_lines(doc) -> None:
	"""With lines, the tax and the total are worked out here; with none, the amount is what was typed."""
	figures = {"taxable": 0, "tax": 0, "cgst": 0, "sgst": 0, "igst": 0}
	kind = ""
	if doc.get("lines"):
		for row in doc.lines:
			if cint(row.quantity) <= 0 or flt(row.rate) < 0:
				frappe.throw(
					_("Row {0}: the quantity must be more than nothing and the rate not negative.").format(
						row.idx
					)
				)
			row.hsn = (row.hsn or "").strip()
			row.taxable, row.tax = (float(x) for x in gst.line(row.quantity, row.rate, row.gst_rate or "0"))
		kind = gst.supply(
			frappe.db.get_single_value("RD Settings", "library_gstin"),
			frappe.db.get_value("RD Vendor", doc.vendor, "gstin"),
		)
		figures = gst.totals([(r.quantity, r.rate, r.gst_rate or "0") for r in doc.lines], kind)
		doc.amount = figures["total"]
	doc.supply = _SUPPLY.get(kind, "")
	doc.taxable_total, doc.tax_total = figures["taxable"], figures["tax"]
	doc.cgst, doc.sgst, doc.igst = figures["cgst"], figures["sgst"], figures["igst"]


def _lines_key(doc) -> list:
	return [tuple(row.get(f) or "" for f in LINE_FIELDS) for row in doc.get("lines") or []]


def _match_lines(doc, po) -> str:
	"""The lines that name an order line: no more billed than ordered or received (all of one book together)."""
	own = {r.name for r in po.lines}
	billed: dict = {}
	for row in doc.lines:
		if row.order_line:
			if row.order_line not in own:
				frappe.throw(_("Row {0}: that line is not on the order {1}.").format(row.idx, po.name))
			billed[row.order_line] = billed.get(row.order_line, 0) + cint(row.quantity)
	return money.lines_match(
		billed, {r.name: cint(r.quantity) for r in po.lines}, {r.name: cint(r.received) for r in po.lines}
	)


def check_invoice(doc) -> None:
	"""RD Invoice.validate: the lines and tax, the order's vendor and budget, a number not used before, and the
	three-way check."""
	_price_lines(doc)
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
			if before.status != "Draft" and (
				any(
					doc.get(f) != before.get(f)
					for f in ("amount", "vendor", "order", "budget", "invoice_number")
				)
				or _lines_key(doc) != _lines_key(before)
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
		# the order's prices are before tax, so with lines it is the taxable value that is checked against it
		billed = doc.taxable_total if doc.get("lines") else doc.amount
		doc.match = money.three_way(billed, po.total, _received_value(doc.order))
		if doc.match == "ok" and doc.get("lines"):
			doc.match = _match_lines(doc, po)
	elif any(r.order_line for r in doc.get("lines") or []):
		frappe.throw(_("Choose the order these lines belong to."))


@frappe.whitelist()
def invoice_lines_from_order(order: str) -> list[dict]:
	"""The lines of an order as invoice lines (what has arrived, or the whole order when nothing has yet)."""
	_staff()
	po = frappe.get_doc("RD Purchase Order", order)
	return [
		{
			"description": r.title,
			"order_line": r.name,
			"hsn": "4901",
			"quantity": cint(r.received) or cint(r.quantity),
			"rate": flt(r.unit_price),
			"gst_rate": "0",
		}
		for r in po.lines
	]


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
