"""The numbers at the top of the Research Desk workspace, for managers: the catalogue, readers,
the research layer, preservation and portal use, each linked to where to act on it.

Computed in a handful of count queries and kept for five minutes, so opening the Desk stays quick
however big the catalogue is.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime, nowdate

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


def compute() -> dict:
	week, month = add_days(nowdate(), -7), add_days(nowdate(), -30)
	count = frappe.db.count
	books = count("RD Item", {"published": 1})
	quality = frappe.db.sql(
		"select avg(ocr_quality) from `tabRD Item` where published = 1 and ocr_quality > 0"
	)[0][0]
	pages = frappe.db.sql(
		"select sum(page_count) from `tabRD Item` where published = 1 and has_page_text = 1"
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


@frappe.whitelist()
def numbers(refresh: int = 0) -> dict:
	frappe.only_for(MANAGERS)
	if not cint(refresh):
		cached = frappe.cache.get_value(CACHE_KEY)
		if cached:
			return cached
	out = compute()
	frappe.cache.set_value(CACHE_KEY, out, expires_in_sec=300)
	return out
