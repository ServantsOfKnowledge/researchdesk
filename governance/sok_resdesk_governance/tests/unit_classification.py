"""Levels and need-to-know (core/classification.py)."""

from sok_resdesk_governance.core.classification import (
	LEVELS,
	STANDARD_LEVELS,
	allowed_levels,
	cleared,
	expand,
	meili_clause,
	rank,
	sql_clause,
)

TREE = {"Directorate": "Secretariat", "District": "Directorate", "Taluk": "District", "Other": "Secretariat2"}


def test_levels_and_the_two_top_ones_need_classified_mode():
	assert [rank(x) for x in LEVELS] == [0, 1, 2, 3, 4]
	assert rank("nonsense") == 0 and rank(None) == 0
	assert allowed_levels(False) == STANDARD_LEVELS and "Secret" not in STANDARD_LEVELS
	assert allowed_levels(True) == LEVELS


def test_a_head_office_sees_downward_never_upward():
	assert expand({"Directorate"}, TREE) == {"Directorate", "District", "Taluk"}
	assert expand({"Taluk"}, TREE) == {"Taluk"}
	assert expand(set(), TREE) == set()


def test_cleared_needs_the_level_and_the_department():
	mine = expand({"District"}, TREE)
	assert cleared(2, mine, 2, "Taluk")
	assert not cleared(1, mine, 2, "Taluk")  # level too low
	assert not cleared(4, mine, 0, "Directorate")  # the office above is not theirs
	assert cleared(0, mine, 0, "")  # no department: any cleared person
	assert cleared(0, set(), 0, "")
	assert not cleared(4, set(), 0, "Taluk")  # no departments, a department-scoped record
	assert cleared(4, None, 4, "Anywhere")  # None = every department (Administrator)


def test_the_filters_say_the_same_in_the_search_engine_and_in_sql():
	assert meili_clause(1, {"A", 'B"c'}) == (
		'(NOT class_rank > 1 AND (department IS EMPTY OR department IS NULL OR department IN ["A", "B\\"c"]))'
	)
	assert meili_clause(4, None) == "(NOT class_rank > 4)"
	assert meili_clause(0, set()) == "(NOT class_rank > 0 AND (department IS EMPTY OR department IS NULL))"
	q = lambda v: "'" + v.replace("'", "''") + "'"  # noqa: E731
	assert sql_clause(2, {"A"}, "i.", q) == (
		"(ifnull(i.class_rank, 0) <= 2 and (ifnull(i.department, '') = '' or i.department in ('A')))"
	)
	assert sql_clause(3, None, "", q) == "(ifnull(class_rank, 0) <= 3)"
