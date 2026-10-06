"""COUNTER Release 5 style usage reports (core/counter.py has the format and what is reported).

    /api/method/sok_resdesk.counter.reports                       which reports are offered
    /api/method/sok_resdesk.counter.report?report_id=TR
          &begin_date=2026-01&end_date=2026-06&format=json|tsv    the Title Master Report

For managers (Settings → Usage Statistics must be on Built-in, which records the page views).
A funder or consortium asks for this; nothing here leaves the server unless a manager sends it.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

import frappe
from frappe import _

from sok_resdesk import access, features
from sok_resdesk.catalogue import base_url, portal_title
from sok_resdesk.core import counter

REPORTS = [
	{
		"Report_Name": counter.REPORT_NAME,
		"Report_ID": counter.REPORT_ID,
		"Release": counter.RELEASE,
		"Report_Description": "Investigations of each book's page, by month. Requests are not recorded.",
		"Path": "/api/method/sok_resdesk.counter.report?report_id=TR",
	}
]


def _platform() -> str:
	return urlparse(base_url()).hostname or "researchdesk"


@frappe.whitelist(methods=["GET"])
def reports() -> list[dict]:
	frappe.only_for(access.MANAGER_ROLES)
	return REPORTS


def usage_rows(begin: date, end: date) -> list[tuple[str, str, int, int]]:
	"""[(item_id, 'YYYY-MM', views, unique views)] from the page-view log, for book pages only."""
	if not frappe.db.exists("DocType", "Web Page View"):
		return []
	rows = frappe.db.sql(
		"""select path, date_format(creation, '%%Y-%%m') as month, count(*) as total,
			sum(is_unique = '1') as uniq
		from `tabWeb Page View`
		where creation >= %s and creation < %s and path like %s
		group by path, month""",
		(begin, frappe.utils.add_days(end, 1), "%library/item/%"),
		as_dict=True,
	)
	merged: dict[tuple[str, str], list[int]] = {}
	for r in rows:
		item_id = r.path.split("library/item/", 1)[-1].split("?")[0].split("/")[0].strip()
		if not item_id:
			continue
		slot = merged.setdefault((item_id, r.month), [0, 0])
		slot[0] += int(r.total or 0)
		slot[1] += int(r.uniq or 0)
	return [(i, m, t, u) for (i, m), (t, u) in merged.items()]


def titles_of(item_ids: list[str]) -> dict[str, dict]:
	if not item_ids:
		return {}
	out = {}
	for r in frappe.get_all(
		"RD Item",
		filters={"name": ("in", item_ids)},
		fields=["name", "title", "publisher", "isbn", "ark", "doi", "visibility"],
	):
		out[r.name] = {
			"title": r.title,
			"publisher": r.publisher or "",
			"isbn": r.isbn or "",
			"ark": r.ark or "",
			"doi": r.doi or "",
			"restricted": r.visibility not in (None, "", "Public"),
		}
	return out


@frappe.whitelist(methods=["GET"])
def report(report_id: str = "TR", begin_date: str = "", end_date: str = "", format: str = "json"):
	"""The Title Master Report for a period (default: the last twelve full months)."""
	frappe.only_for(access.MANAGER_ROLES)
	if (report_id or "TR").upper() != counter.REPORT_ID:
		frappe.throw(_("Only the Title Master Report (TR) is offered."), frappe.ValidationError)
	if not features.on("statistics"):
		frappe.throw(_("Usage statistics are switched off for this library."), frappe.ValidationError)
	try:
		default_begin, default_end = counter.default_period(frappe.utils.getdate())
		begin = counter.parse_month(begin_date) if begin_date else default_begin
		end = counter.parse_month(end_date, end=True) if end_date else default_end
	except counter.BadDate:
		frappe.throw(_("Dates are YYYY-MM or YYYY-MM-DD."), frappe.ValidationError)
	if end < begin:
		frappe.throw(_("The end date is before the begin date."), frappe.ValidationError)
	usage = usage_rows(begin, end)
	data = counter.build_report(
		platform=_platform(),
		institution=portal_title(),
		begin=begin,
		end=end,
		usage=usage,
		titles=titles_of(sorted({u[0] for u in usage})),
	)
	if (format or "json").lower() == "tsv":
		frappe.response["type"] = "download"
		frappe.response["filename"] = f"TR_{begin.isoformat()}_{end.isoformat()}.tsv"
		frappe.response["filecontent"] = counter.to_tsv(data).encode("utf-8")
		return None
	return data
