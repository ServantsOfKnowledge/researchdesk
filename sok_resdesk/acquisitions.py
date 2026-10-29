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

from sok_resdesk import features
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
	doc = frappe.get_doc("RD Purchase Order", order)
	doc.lock()  # two deliveries entered together must not make the copies twice
	doc.reload()
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
