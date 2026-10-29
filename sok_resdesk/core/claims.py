"""Claims to vendors: which orders are overdue and the letter that asks for them. Pure Python."""

from __future__ import annotations

from datetime import date

REPEAT_DAYS = 14  # a claim is not made again until this many days after the last one


def due_for_claim(
	expected_on: date | None, claimed_on: date | None, today: date, grace_days: int = 0
) -> bool:
	"""An order or issue that is past its date (plus any grace) and not claimed in the last REPEAT_DAYS."""
	if not expected_on or (today - expected_on).days <= max(int(grace_days or 0), 0):
		return False
	return not claimed_on or (today - claimed_on).days >= REPEAT_DAYS


def _day(d) -> str:
	return f"{d:%d %b %Y}" if d else "-"


def letter(library: str, vendor: str, orders: list[dict], issues: list[dict], today: date) -> str:
	"""Plain text to paste into an email or print. `orders`: {name, order_date, expected_date, lines:[(title,
	outstanding quantity)]}; `issues`: {title, label, expected_on}."""
	out = [library or "", _day(today), "", f"To: {vendor}", "", "Dear Sir or Madam,", ""]
	out.append("We have not received the following. Please tell us when they will be sent, or cancel them.")
	if orders:
		out += ["", "Orders:"]
		for o in orders:
			what = "; ".join(f"{q} x {t}" for t, q in o["lines"])
			out.append(
				f"- {o['name']} of {_day(o['order_date'])}, expected {_day(o['expected_date'])}: {what}"
			)
	if issues:
		out += ["", "Periodicals:"]
		for i in issues:
			out.append(f"- {i['title']}, {i['label']} (expected {_day(i['expected_on'])})")
	out += ["", "Thank you.", library or ""]
	return "\n".join(out)
