from datetime import date

from sok_resdesk_governance.core.retention import due_on, governing


def test_the_period_counts_from_the_year_of_the_record():
	assert due_on("Year of the record", 10, 1995, date(2026, 1, 1)) == date(2005, 12, 31)


def test_a_record_with_no_year_has_no_due_date_on_that_basis():
	assert due_on("Year of the record", 10, None, date(2026, 1, 1)) is None


def test_the_period_counts_from_the_day_added_and_survives_a_leap_day():
	assert due_on("Date added", 5, None, date(2020, 3, 4)) == date(2025, 3, 4)
	assert due_on("Date added", 1, None, date(2020, 2, 29)) == date(2021, 2, 28)


def test_the_longest_period_governs():
	a = ("short", date(2025, 1, 1), "Destroy")
	b = ("long", date(2040, 1, 1), "Transfer to archives")
	assert governing([a, b]) == b


def test_a_tie_goes_to_the_more_cautious_action():
	d = date(2030, 1, 1)
	assert (
		governing([("a", d, "Destroy"), ("b", d, "Review only"), ("c", d, "Transfer to archives")])[2]
		== "Review only"
	)


def test_no_rule_no_answer():
	assert governing([]) is None


def test_an_impossible_year_gives_no_date_instead_of_an_error():
	assert due_on("Year of the record", 10, 9999, date(2026, 1, 1)) is None
	assert due_on("Date added", 100000, None, date(2026, 1, 1)) is None
