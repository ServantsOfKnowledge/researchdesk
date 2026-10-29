"""Budgets and invoices as plain arithmetic (no Frappe): what an order has committed, what is spent, what is left."""

from __future__ import annotations

ACTIVE_ORDERS = ("Ordered", "Part Received", "Received")
TOLERANCE = 0.05  # an invoice may be this much above the value of what arrived before a manager must look


def commitment(order_total: float, status: str, invoiced: float) -> float:
	"""What an order still holds back from the budget: its total less what has been invoiced against it
	(that part is spent, not held). A draft or cancelled order holds nothing."""
	if status not in ACTIVE_ORDERS:
		return 0.0
	return round(max(float(order_total or 0) - float(invoiced or 0), 0.0), 2)


def summary(amount: float, orders: list[tuple[float, str, float]], invoiced: float) -> dict:
	"""`orders` are (total, status, invoiced against it); `invoiced` is every invoice on the budget."""
	committed = round(sum(commitment(*o) for o in orders), 2)
	spent = round(float(invoiced or 0), 2)
	return {
		"amount": round(float(amount or 0), 2),
		"committed": committed,
		"spent": spent,
		"used": round(committed + spent, 2),
		"remaining": round(float(amount or 0) - committed - spent, 2),
	}


def fits(amount: float, orders: list[tuple[float, str, float]], invoiced: float, extra: float) -> bool:
	"""Whether `extra` more can be committed without going over the budget."""
	return summary(amount, orders, invoiced)["remaining"] - float(extra or 0) >= -0.005


def received_value(lines: list[tuple[int, float]]) -> float:
	"""The value of what arrived: (quantity received, unit price) per line."""
	return round(sum(int(q or 0) * float(p or 0) for q, p in lines), 2)


def three_way(
	invoice_amount: float, order_total: float, received: float, tolerance: float = TOLERANCE
) -> str:
	"""Order, receipt and invoice agree ("ok"), or the invoice asks for more than the books that came are
	worth ("over received") or more than was ordered ("over order")."""
	amount = float(invoice_amount or 0)
	if amount > float(order_total or 0) * (1 + tolerance) + 0.005:
		return "over order"
	if amount > float(received or 0) * (1 + tolerance) + 0.005:
		return "over received"
	return "ok"
