"""0.65: COUNTER Release 5 style Title Master Report from page-view counts."""

import json
from datetime import UTC, date, datetime

import pytest

from sok_resdesk.core import counter

WHEN = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
TITLES = {
	"b1": {"title": "Beta", "publisher": "P", "isbn": "123", "ark": "ark:/1/b1", "doi": "10.1/x"},
	"a1": {"title": "alpha", "restricted": True},
}
USAGE = [("b1", "2026-01", 10, 4), ("b1", "2026-03", 2, 2), ("a1", "2026-02", 5, 3), ("zz", "2025-12", 9, 9)]


def report(**kw):
	args = dict(
		platform="lib.example.org",
		institution="Lib",
		begin=date(2026, 1, 1),
		end=date(2026, 3, 31),
		usage=USAGE,
		titles=TITLES,
		created=WHEN,
	)
	args.update(kw)
	return counter.build_report(**args)


def test_months_and_defaults():
	assert counter.months_between(date(2025, 11, 5), date(2026, 2, 1)) == [
		"2025-11",
		"2025-12",
		"2026-01",
		"2026-02",
	]
	assert counter.default_period(date(2026, 7, 15)) == (date(2025, 7, 1), date(2026, 6, 30))
	assert counter.default_period(date(2026, 1, 3)) == (date(2025, 1, 1), date(2025, 12, 31))


def test_dates_parse_as_month_or_day():
	assert counter.parse_month("2026-02") == date(2026, 2, 1)
	assert counter.parse_month("2026-02", end=True) == date(2026, 2, 28)
	assert counter.parse_month("2026-02-10") == date(2026, 2, 10)
	for bad in ("", "2026", "2026-13", "2026-02-30", "x"):
		with pytest.raises(counter.BadDate):
			counter.parse_month(bad)


def test_report_has_the_counter_header_and_sorted_items():
	r = report()
	h = r["Report_Header"]
	assert (h["Report_ID"], h["Release"], h["Report_Name"]) == ("TR", "5", "Title Master Report")
	assert h["Institution_Name"] == "Lib" and h["Created"] == "2026-07-01T12:00:00Z"
	assert {f["Name"] for f in h["Report_Filters"]} == {"Begin_Date", "End_Date", "Metric_Type"}
	titles = [i["Title"] for i in r["Report_Items"]]
	assert titles == ["alpha", "Beta"]  # case-insensitive order; "zz" is outside the period
	assert json.loads(json.dumps(r)) == r


def test_each_month_lists_both_investigation_metrics():
	r = report()
	beta = next(i for i in r["Report_Items"] if i["Title"] == "Beta")
	assert [p["Period"]["Begin_Date"] for p in beta["Performance"]] == ["2026-01-01", "2026-03-01"]
	jan = beta["Performance"][0]
	assert jan["Period"]["End_Date"] == "2026-01-31"
	assert jan["Instance"] == [
		{"Metric_Type": "Total_Item_Investigations", "Count": 10},
		{"Metric_Type": "Unique_Item_Investigations", "Count": 4},
	]
	ids = {i["Type"]: i["Value"] for i in beta["Item_ID"]}
	assert ids["Proprietary"] == "lib.example.org:b1" and ids["ISBN"] == "123" and ids["DOI"] == "10.1/x"
	assert ids["URI"] == "ark:/1/b1"


def test_access_type_follows_whether_the_book_is_restricted():
	r = report()
	by = {i["Title"]: i for i in r["Report_Items"]}
	assert by["alpha"]["Access_Type"] == "Controlled" and by["Beta"]["Access_Type"] == "OA_Gold"


def test_it_says_requests_are_not_recorded_and_flags_an_empty_period():
	codes = [e["Code"] for e in report()["Report_Header"]["Exceptions"]]
	assert codes == [3040]
	r = report(usage=[])
	assert [e["Code"] for e in r["Report_Header"]["Exceptions"]] == [3040, 3030]
	assert r["Report_Items"] == []


def test_tsv_has_a_header_block_then_two_rows_per_title():
	lines = counter.to_tsv(report()).rstrip("\n").split("\n")
	assert lines[0] == "Report_Name\tTitle Master Report"
	assert "Reporting_Period\t2026-01-01 to 2026-03-31" in lines
	blank = lines.index("")
	head = lines[blank + 1].split("\t")
	assert head[-3:] == ["2026-01", "2026-02", "2026-03"]
	rows = lines[blank + 2 :]
	assert len(rows) == 4  # two titles x two metrics
	beta_total = next(r.split("\t") for r in rows if r.startswith("Beta") and "Total_" in r)
	assert beta_total[head.index("Reporting_Period_Total")] == "12"
	assert beta_total[-3:] == ["10", "0", "2"]


def test_tabs_and_newlines_in_titles_do_not_break_the_table():
	r = report(titles={"b1": {"title": "A\tB\nC"}}, usage=[("b1", "2026-01", 1, 1)])
	text = counter.to_tsv(r)
	assert "A B C" in text
