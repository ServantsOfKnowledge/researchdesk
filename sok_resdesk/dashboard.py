"""The numbers at the top of the Research Desk workspace, for managers: the catalogue, readers,
the research layer, preservation and portal use, each linked to where to act on it.

Counted in a handful of queries by a background job (hourly, and again when the last count is more
than five minutes old and someone opens the Desk). Opening the Desk shows the last count at once,
so it stays quick however big the catalogue is. `timings()` shows which count is slow.
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime, nowdate

from sok_resdesk.ratelimit import rate_limit

MANAGERS = ("System Manager", "ResDesk Manager")
CACHE_KEY = "resdesk:dashboard"
READER = "ResDesk Reader"
PROOFREADER = "ResDesk Proofreader"


def _role_count(role: str) -> int:
	return cint(
		frappe.db.sql(
			"""select count(distinct u.name) from `tabUser` u join `tabHas Role` r on r.parent = u.name
			and r.parenttype = 'User' where r.role = %s and u.enabled = 1 and u.name not in ('Administrator', 'Guest')""",
			role,
		)[0][0]
	)


def _logins(since) -> int:
	if not frappe.db.exists("DocType", "Activity Log"):
		return 0
	return cint(
		frappe.db.sql(
			"""select count(distinct user) from `tabActivity Log`
			where operation = 'Login' and status = 'Success' and creation >= %s""",
			since,
		)[0][0]
	)


CLEARED_ONLY = "Cleared only"
NOT_CLASSIFIED = f"ifnull(visibility, '') != '{CLEARED_ONLY}'"


def count(doctype: str, filters: dict | None = None) -> int:
	"""A count for the dashboard, which is kept for everyone: classified records are not in any number
	(they are not on the portal), nor are the notes and page text that belong to them."""
	filters = dict(filters or {})
	if doctype == "RD Item":
		filters["visibility"] = ("!=", CLEARED_ONLY)
	elif doctype in ("RD Annotation", "RD Page Text"):
		hidden = frappe.get_all("RD Item", filters={"visibility": CLEARED_ONLY}, pluck="name")
		if hidden:
			filters["item"] = ("not in", hidden)
	return frappe.db.count(doctype, filters)


def compute() -> dict:
	week, month = add_days(nowdate(), -7), add_days(nowdate(), -30)
	books = count("RD Item", {"published": 1})
	quality = frappe.db.sql(
		f"select avg(ocr_quality) from `tabRD Item` where published = 1 and ocr_quality > 0 and {NOT_CLASSIFIED}"
	)[0][0]
	pages = frappe.db.sql(
		f"select sum(page_count) from `tabRD Item` where published = 1 and has_page_text = 1 and {NOT_CLASSIFIED}"
	)[0][0]
	groups = [
		{
			"title": _("Catalogue"),
			"cards": [
				{
					"label": _("Books on the portal"),
					"value": books,
					"sub": _("{0} added this week").format(
						count("RD Item", {"published": 1, "creation": (">=", week)})
					),
					"route": ["List", "RD Item", {"published": 1}],
				},
				{
					"label": _("Pages searchable"),
					"value": cint(pages),
					"sub": _("in {0} books with text").format(
						count("RD Item", {"published": 1, "has_page_text": 1})
					),
					"route": ["List", "RD Item", {"has_page_text": 1}],
				},
				{
					"label": _("Waiting for search"),
					"value": count("RD Item", {"published": 1, "indexed_on": ("is", "not set")}),
					"sub": _("books not yet findable"),
					"route": ["resdesk-jobs"],
				},
				{
					"label": _("OCR quality"),
					"value": round(quality or 0),
					"suffix": "/100",
					"sub": _("average; {0} books under 50").format(
						count("RD Item", {"published": 1, "ocr_quality": ("between", [1, 49])})
					),
					"route": ["List", "RD Item", {"ocr_quality": ["between", [1, 49]]}],
				},
			],
		},
		{
			"title": _("Readers"),
			"cards": [
				{
					"label": _("Readers"),
					"value": _role_count(READER),
					"sub": _("{0} new accounts this month").format(
						count("User", {"creation": (">=", month), "user_type": "Website User", "enabled": 1})
					),
					"route": ["resdesk-people"],
				},
				{
					"label": _("Logged in this week"),
					"value": _logins(week),
					"sub": _("{0} this month").format(_logins(month)),
					"route": ["List", "Activity Log", {"operation": "Login"}],
				},
				{
					"label": _("Sign-ups waiting"),
					"value": count("RD Reader Request", {"status": "Pending"}),
					"sub": _("to approve or reject"),
					"route": ["resdesk-people"],
					"alert": True,
				},
				{
					"label": _("Proofreaders"),
					"value": _role_count(PROOFREADER),
					"sub": _("volunteers correcting text"),
					"route": ["resdesk-people"],
				},
			],
		},
		{
			"title": _("Research"),
			"cards": [
				{
					"label": _("Notes this month"),
					"value": count("RD Annotation", {"creation": (">=", month)}),
					"sub": _("{0} in all").format(count("RD Annotation")),
					"route": ["List", "RD Annotation"],
				},
				{
					"label": _("Public notes to review"),
					"value": count("RD Annotation", {"visibility": "Public", "review_status": "Pending"}),
					"sub": _("approve or reject"),
					"route": ["List", "RD Annotation", {"review_status": "Pending"}],
					"alert": True,
				},
				{
					"label": _("OCR errors reported"),
					"value": count("RD Annotation", {"kind": "OCR error", "creation": (">=", month)}),
					"sub": _("this month"),
					"url": "/library/proofread",
				},
				{
					"label": _("Pages proofread"),
					"value": count(
						"RD Page Text", {"is_current": 1, "status": ("in", ["Proofread", "Validated"])}
					),
					"sub": _("{0} validated").format(
						count("RD Page Text", {"is_current": 1, "status": "Validated"})
					),
					"route": ["List", "RD Page Text", {"is_current": 1}],
				},
			],
		},
		{
			"title": _("Preservation"),
			"cards": [
				{
					"label": _("Books preserved"),
					"value": count("RD Item", {"preservation_status": "Preserved"}),
					"sub": _("verified copies here"),
					"route": ["List", "RD Item", {"preservation_status": "Preserved"}],
				},
				{
					"label": _("Failed checks"),
					"value": count("RD Item", {"preservation_status": ("in", ["Failed check", "Missing"])}),
					"sub": _("copies to repair"),
					"route": [
						"List",
						"RD Item",
						{"preservation_status": ["in", ["Failed check", "Missing"]]},
					],
					"alert": True,
				},
			],
		},
	]
	usage = _usage()
	if usage:
		groups.append(usage)
	# data here that a switched-off feature would handle (Settings → Features)
	from sok_resdesk import features

	hints = features.suggestions()
	if hints:
		groups.append(
			{
				"title": _("Features to consider"),
				"cards": [
					{
						"value": h["count"],
						"label": h["label"],
						"sub": _("switched off: see Settings → Features"),
						"route": ["Form", "RD Settings"],
						"alert": True,
					}
					for h in hints
				],
			}
		)
	return {"groups": groups, "as_of": str(now_datetime())[:16]}


def _usage() -> dict | None:
	s = frappe.get_cached_doc("RD Settings")
	provider = s.get("analytics_provider") or "Off"
	dashboard = s.get("analytics_dashboard") or ""
	if provider == "Built-in":
		from sok_resdesk.analytics import page_views

		pv = page_views(7)
		if pv is None:
			return None
		cards = [
			{
				"label": _("Page views this week"),
				"value": pv["views"],
				"sub": _("{0} visitors").format(pv["visitors"]),
				"route": ["List", "Web Page View"],
			},
		]
		for t in pv["top"][:3]:
			cards.append(
				{
					"label": t.title[:60],
					"value": t.views,
					"sub": _("views this week"),
					"url": f"/library/item/{t.item}",
				}
			)
		return {"title": _("Portal use"), "cards": cards}
	if provider in ("PostHog", "Plausible", "Umami"):
		return {
			"title": _("Portal use"),
			"cards": [
				{
					"label": _("Statistics in {0}").format(provider),
					"value": "↗",
					"sub": _("open the dashboard"),
					"url": dashboard or s.get("analytics_host") or "",
				}
			],
		}
	return None


FRESH_SECONDS = 300
JOB_ID = "resdesk-dashboard"


def rebuild() -> dict:
	"""Count everything and keep the answer. Runs in the background (and hourly), so opening the Desk
	never waits for the counts of a big catalogue."""
	out = compute()
	out["at"] = time.time()
	frappe.cache.set_value(CACHE_KEY, out, expires_in_sec=7 * 24 * 3600)
	return out


@frappe.whitelist()
@rate_limit(limit=60, seconds=60)
def numbers(refresh: int = 0) -> dict:
	"""The last counts at once, however old; a newer set is counted in the background when they are more
	than five minutes old. Only the very first time (or with `refresh`) does the caller wait."""
	frappe.only_for(MANAGERS)
	cached = None if cint(refresh) else frappe.cache.get_value(CACHE_KEY)
	if not cached:
		return rebuild()
	if time.time() - cached.get("at", 0) > FRESH_SECONDS:
		frappe.enqueue(
			"sok_resdesk.dashboard.rebuild", queue="short", job_id=JOB_ID, deduplicate=True, timeout=600
		)
	return cached


def timings() -> None:
	"""Which count is slow? ./resdesk.sh bench execute sok_resdesk.dashboard.timings"""
	slow = []

	def timed(fn, name):
		def wrapper(*args, **kwargs):
			start = time.time()
			try:
				return fn(*args, **kwargs)
			finally:
				slow.append((time.time() - start, name, " ".join(str(args)[:140].split())))

		return wrapper

	frappe.db.sql = timed(frappe.db.sql, "sql")
	frappe.db.count = timed(frappe.db.count, "count")
	start = time.time()
	try:
		compute()
	finally:
		del frappe.db.sql
		del frappe.db.count
	print(f"all the counts: {time.time() - start:.1f} s")
	for seconds, name, what in sorted(slow, reverse=True)[:8]:
		print(f"{seconds:6.2f} s  {name}  {what}")
