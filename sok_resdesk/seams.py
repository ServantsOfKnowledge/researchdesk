"""The places core lets an optional governance layer plug in (docs/development.md#the-governance-seam).

Core never imports the governance modules. It asks here, and the answer comes from whatever the
installed apps list in their hooks.py. With nothing listed the library is not governed: no event is
kept, nobody is cleared for a classified record (it stays hidden, never shown by default), and the
Server page has no extra checks. `tests/unit_boundaries.py` fails when core imports governance.

Hooks (each a list of dotted paths, merged across apps). Booleans are true if any app says so; for the
others the first app listed wins, so only one app should provide them:
  resdesk_event_sinks    fn(event, item, detail)     something happened that a log may want
  resdesk_governed       fn() -> bool                the governance layer is switched on
  resdesk_item_cleared   fn(item, user) -> bool      this person is cleared for the record
  resdesk_cleared_sql    fn(item_expr, user) -> str  SQL: the same, for a column in a query
  resdesk_item_scope     fn(item) -> (rank, dept)    the record's level and department
  resdesk_search_clause  fn() -> str                 the search engine's filter for what they may see
  resdesk_health_checks  fn() -> [(key, label, state, text)]   lines for the Server page
"""

from __future__ import annotations

import os

import frappe


def _fns(hook: str) -> list:
	return [frappe.get_attr(path) for path in frappe.get_hooks(hook) or []]


def merged(hook: str) -> dict:
	"""What add-on apps contribute under `hook` (each hook returns a dict); empty with none."""
	out: dict = {}
	for fn in _fns(hook):
		out.update(fn())
	return out


def emit(event: str, item: str = "", detail: str = "") -> None:
	for fn in _fns("resdesk_event_sinks"):
		try:
			fn(event, item, detail)
		except Exception:  # a broken sink must not stop a reader; the other hooks fail closed instead
			frappe.log_error(title="Research Desk: an event sink failed")


def governed() -> bool:
	return any(fn() for fn in _fns("resdesk_governed"))


def cleared(item: str | None, user: str | None = None) -> bool:
	return any(fn(item, user) for fn in _fns("resdesk_item_cleared"))


def cleared_sql(item_expr: str, user: str | None = None) -> str:
	for fn in _fns("resdesk_cleared_sql"):
		return fn(item_expr, user)
	return "1=0"


def scope(item: str | None) -> tuple[int, str]:
	"""(level number, department) of a classified record; (0, "") when there is none or no governance."""
	for fn in _fns("resdesk_item_scope"):
		return fn(item)
	return (0, "")


def search_clause() -> str:
	for fn in _fns("resdesk_search_clause"):
		return fn()
	return ""


def health_checks() -> list[tuple]:
	out: list[tuple] = []
	for fn in _fns("resdesk_health_checks"):
		out += fn()
	return out


def classified() -> bool:
	"""The site is run as a Classified installation (site configuration or RESDESK_CLASSIFIED=1): core
	refuses what needs the outside world. The guard that enforces it is the governance layer's."""
	return bool(frappe.conf.get("resdesk_classified") or os.environ.get("RESDESK_CLASSIFIED") == "1")
