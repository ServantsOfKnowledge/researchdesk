"""Disclosure requests, the rules that need no database (docs/governance.md#disclosure-requests-and-redaction)."""

from __future__ import annotations

from datetime import date, timedelta

DISCLOSE, REDACTED, WITHHOLD = "Disclose", "Disclose redacted", "Withhold"
DECISIONS = (DISCLOSE, REDACTED, WITHHOLD)


def due_on(received: date, days: int) -> date:
	"""The day the reply is owed: `days` calendar days after the request arrived (at least one)."""
	return received + timedelta(days=max(int(days or 0), 1))


def box_ok(left, top, width, height) -> bool:
	"""A box is given in percent of the page, wholly on it and not empty."""
	try:
		left, top, width, height = (float(v) for v in (left, top, width, height))
	except (TypeError, ValueError):
		return False
	return (
		left >= 0
		and top >= 0
		and width > 0
		and height > 0
		and left + width <= 100.01
		and top + height <= 100.01
	)


def problems(records: list[dict], boxes: list[dict]) -> list[str]:
	"""What stops these decisions being final: `records` have item, decision, ground; `boxes` have item,
	page, left, top, width, height."""
	out, decided = [], {}
	for r in records:
		if r["item"] in decided:
			out.append(f"{r['item']} is listed twice.")
		decided[r["item"]] = r.get("decision") or ""
		if decided[r["item"]] not in DECISIONS:
			out.append(f"{r['item']} has no decision.")
		elif decided[r["item"]] != DISCLOSE and not (r.get("ground") or "").strip():
			out.append(f"{r['item']}: say which ground allows keeping back or covering part of it.")
	for item, decision in decided.items():
		if decision == REDACTED and not any(b["item"] == item for b in boxes):
			out.append(f"{item} is to be disclosed redacted but nothing is covered.")
	for b in boxes:
		if decided.get(b["item"]) != REDACTED:
			out.append(
				f"{b['item']} page {b.get('page')}: covered, but the record is not set to Disclose redacted."
			)
		elif int(b.get("page") or 0) < 1:
			out.append(f"{b['item']}: a page number is needed.")
		if not box_ok(b.get("left"), b.get("top"), b.get("width"), b.get("height")):
			out.append(f"{b['item']} page {b.get('page')}: a box must lie wholly on the page (percent).")
	return out


def pages_off(boxes: list[dict], counts: dict[str, int]) -> list[str]:
	"""Boxes on a page the record does not have: such a box would cover nothing."""
	return [
		f"{b['item']}: a box is on page {b.get('page')}, but the record has {counts.get(b['item'], 0)} pages."
		for b in boxes
		if int(b.get("page") or 0) > counts.get(b["item"], 0)
	]
