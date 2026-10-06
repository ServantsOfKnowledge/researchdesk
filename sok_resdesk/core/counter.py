"""COUNTER Release 5 style usage reports from the portal's page-view counts.

Libraries that report their use to funders or consortia are asked for COUNTER reports. The portal
records page views of each book (Settings → Usage Statistics → Built-in), so what can be reported
honestly is the **Title Master Report (TR)** with the two *investigation* metrics:

* ``Total_Item_Investigations``: every view of a book's page
* ``Unique_Item_Investigations``: the first view of that book by a visitor in a day

*Requests* (a file opened or downloaded) are not recorded, so the report says so (exception 3040)
instead of leaving a reader to assume. COUNTER's own filters (robots, double-clicks) are not
applied beyond what the page-view log does. Pure Python (no Frappe), unit-tested directly.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime

RELEASE = "5"
REPORT_ID = "TR"
REPORT_NAME = "Title Master Report"
METRICS = ("Total_Item_Investigations", "Unique_Item_Investigations")
EXCEPTIONS = {
	3030: ("Warning", "No Usage Available for Requested Dates"),
	3040: ("Warning", "Partial Data Returned"),
	3060: ("Error", "Invalid Report Filter Value"),
}
NOT_RECORDED = (
	"Requests (files opened or downloaded) are not recorded by this platform; "
	"only Total_Item_Investigations and Unique_Item_Investigations are reported."
)


class BadDate(ValueError):
	pass


def parse_month(value: str, end: bool = False) -> date:
	"""'2026-03' or '2026-03-15' -> a date (the first / last day of a bare month)."""
	m = re.fullmatch(r"\s*(\d{4})-(\d{2})(?:-(\d{2}))?\s*", value or "")
	if not m:
		raise BadDate(value)
	y, mo = int(m.group(1)), int(m.group(2))
	if not 1 <= mo <= 12:
		raise BadDate(value)
	last = calendar.monthrange(y, mo)[1]
	day = int(m.group(3)) if m.group(3) else (last if end else 1)
	if not 1 <= day <= last:
		raise BadDate(value)
	return date(y, mo, day)


def default_period(today: date) -> tuple[date, date]:
	"""The last twelve full months."""
	y, m = today.year, today.month - 1
	if m == 0:
		y, m = y - 1, 12
	end = date(y, m, calendar.monthrange(y, m)[1])
	sy, sm = y, m - 11
	if sm <= 0:
		sy, sm = sy - 1, sm + 12
	return date(sy, sm, 1), end


def months_between(begin: date, end: date) -> list[str]:
	"""['2026-01', '2026-02', …] from begin's month to end's month."""
	out, y, m = [], begin.year, begin.month
	while (y, m) <= (end.year, end.month):
		out.append(f"{y:04d}-{m:02d}")
		m += 1
		if m == 13:
			y, m = y + 1, 1
	return out


def _period(month: str) -> dict:
	y, m = int(month[:4]), int(month[5:])
	return {
		"Begin_Date": f"{month}-01",
		"End_Date": f"{month}-{calendar.monthrange(y, m)[1]:02d}",
	}


def build_report(
	*,
	platform: str,
	institution: str,
	begin: date,
	end: date,
	usage: list[tuple[str, str, int, int]],
	titles: dict[str, dict],
	created: datetime | None = None,
	creator: str = "SOK Research Desk",
) -> dict:
	"""The report as COUNTER JSON.

	usage: (item_id, 'YYYY-MM', total views, unique views); titles: item_id -> {title, publisher,
	isbn, ark, doi, type}. Items with no usage in the period are left out, as COUNTER says.
	"""
	months = months_between(begin, end)
	per_item: dict[str, dict[str, tuple[int, int]]] = {}
	for item_id, month, total, unique in usage:
		if month in months:
			per_item.setdefault(item_id, {})[month] = (int(total), int(unique))
	items = []
	for item_id in sorted(per_item, key=lambda i: (titles.get(i, {}).get("title") or i).lower()):
		meta = titles.get(item_id, {})
		ids = [{"Type": "Proprietary", "Value": f"{platform}:{item_id}"}]
		for kind, key in (("ISBN", "isbn"), ("DOI", "doi"), ("URI", "ark")):
			if meta.get(key):
				ids.append({"Type": kind, "Value": meta[key]})
		performance = []
		for month in months:
			if month not in per_item[item_id]:
				continue
			total, unique = per_item[item_id][month]
			performance.append(
				{
					"Period": _period(month),
					"Instance": [
						{"Metric_Type": "Total_Item_Investigations", "Count": total},
						{"Metric_Type": "Unique_Item_Investigations", "Count": unique},
					],
				}
			)
		items.append(
			{
				"Title": meta.get("title") or item_id,
				"Item_ID": ids,
				"Platform": platform,
				"Publisher": meta.get("publisher") or "",
				"Data_Type": meta.get("type") or "Book",
				"Section_Type": "Book",
				"Access_Type": "Controlled" if meta.get("restricted") else "OA_Gold",
				"Access_Method": "Regular",
				"Performance": performance,
			}
		)
	exceptions = [
		{
			"Code": 3040,
			"Severity": EXCEPTIONS[3040][0],
			"Message": EXCEPTIONS[3040][1],
			"Data": NOT_RECORDED,
		}
	]
	if not items:
		exceptions.append(
			{
				"Code": 3030,
				"Severity": EXCEPTIONS[3030][0],
				"Message": EXCEPTIONS[3030][1],
				"Data": f"{begin.isoformat()} to {end.isoformat()}",
			}
		)
	created = created or datetime.now(UTC)
	return {
		"Report_Header": {
			"Created": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
			"Created_By": creator,
			"Customer_ID": platform,
			"Report_ID": REPORT_ID,
			"Release": RELEASE,
			"Report_Name": REPORT_NAME,
			"Institution_Name": institution,
			"Institution_ID": [{"Type": "Proprietary", "Value": platform}],
			"Report_Filters": [
				{"Name": "Begin_Date", "Value": begin.isoformat()},
				{"Name": "End_Date", "Value": end.isoformat()},
				{"Name": "Metric_Type", "Value": "|".join(METRICS)},
			],
			"Report_Attributes": [],
			"Exceptions": exceptions,
		},
		"Report_Items": items,
	}


def to_tsv(report: dict) -> str:
	"""The tabular form librarians open in a spreadsheet: the header block, a blank row, then rows."""
	h = report["Report_Header"]
	window = {f["Name"]: f["Value"] for f in h["Report_Filters"]}
	filters = "; ".join(f"{f['Name']}={f['Value']}" for f in h["Report_Filters"])
	lines = [
		("Report_Name", h["Report_Name"]),
		("Report_ID", h["Report_ID"]),
		("Release", h["Release"]),
		("Institution_Name", h["Institution_Name"]),
		("Institution_ID", "; ".join(f"{i['Type']}:{i['Value']}" for i in h["Institution_ID"])),
		("Metric_Types", "; ".join(METRICS)),
		("Report_Filters", filters),
		("Report_Attributes", ""),
		("Exceptions", "; ".join(f"{e['Code']}: {e['Message']} ({e['Data']})" for e in h["Exceptions"])),
		("Reporting_Period", f"{window['Begin_Date']} to {window['End_Date']}"),
		("Created", h["Created"]),
		("Created_By", h["Created_By"]),
	]
	rows = ["\t".join(_cell(c) for c in pair) for pair in lines]
	rows.append("")
	months = months_between_headers(report)
	head = [
		"Title",
		"Publisher",
		"Platform",
		"Proprietary_ID",
		"DOI",
		"ISBN",
		"URI",
		"Data_Type",
		"Section_Type",
		"Access_Type",
		"Access_Method",
		"Metric_Type",
		"Reporting_Period_Total",
		*months,
	]
	rows.append("\t".join(head))
	for item in report["Report_Items"]:
		ids = {i["Type"]: i["Value"] for i in item["Item_ID"]}
		by_month = {}
		for p in item["Performance"]:
			month = p["Period"]["Begin_Date"][:7]
			for inst in p["Instance"]:
				by_month.setdefault(inst["Metric_Type"], {})[month] = inst["Count"]
		for metric in METRICS:
			counts = by_month.get(metric, {})
			cells = [
				item["Title"],
				item["Publisher"],
				item["Platform"],
				ids.get("Proprietary", ""),
				ids.get("DOI", ""),
				ids.get("ISBN", ""),
				ids.get("URI", ""),
				item["Data_Type"],
				item["Section_Type"],
				item["Access_Type"],
				item["Access_Method"],
				metric,
				str(sum(counts.values())),
				*[str(counts.get(m, 0)) for m in months],
			]
			rows.append("\t".join(_cell(c) for c in cells))
	return "\n".join(rows) + "\n"


def months_between_headers(report: dict) -> list[str]:
	f = {x["Name"]: x["Value"] for x in report["Report_Header"]["Report_Filters"]}
	return months_between(date.fromisoformat(f["Begin_Date"]), date.fromisoformat(f["End_Date"]))


def _cell(value) -> str:
	return str(value).replace("\t", " ").replace("\n", " ").replace("\r", " ")
