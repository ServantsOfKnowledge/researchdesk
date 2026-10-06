"""0.65: SRU 1.2 over the catalogue: CQL in, SQL conditions and XML out."""

from xml.etree import ElementTree as ET

import pytest

from sok_resdesk.core import sru

NS = {"s": sru.SRU_NS}


def sql(q):
	return sru.to_sql(sru.parse(q))


def test_a_bare_word_searches_title_author_and_description():
	cond, params = sql("kanakadasa")
	assert "title" in cond and "creator_display" in cond and "description" in cond
	assert params and all(p == "%kanakadasa%" for p in params)


def test_index_relation_and_value():
	cond, params = sql('dc.title = "Old book"')
	assert "title" in cond and "creator_display" not in cond
	assert params[0] == "%Old book%"
	cond, params = sql("author=Basava")
	assert "creator_display" in cond and params == ["%Basava%"]


def test_all_needs_every_word_any_needs_one():
	cond, params = sql('title all "red fort"')
	assert cond.count(" and ") == 1 and params.count("%red%") == 2 and params.count("%fort%") == 2
	cond, params = sql('title any "red fort"')
	assert " or " in cond


def test_exact_is_equality_and_adj_is_a_phrase():
	cond, params = sql('title exact "Vachanas"')
	assert "= %s" in cond and params[0] == "Vachanas"
	cond, params = sql('title adj "red fort"')
	assert params[0] == "%red fort%"


def test_boolean_operators_join_left_to_right_and_brackets_group():
	cond, params = sql("title=a and author=b or subject=c")
	assert cond.startswith("((") and " and " in cond and " or " in cond
	assert params == ["%a%", "%a%", "%b%", "%c%"]  # title searches title and alt title
	cond, _params = sql("title=a and (author=b or author=c)")
	assert cond.count("(") > 3
	cond, _params = sql("title=a not author=b")
	assert " and not " in cond


def test_subject_searches_the_child_table_and_year_is_numeric():
	cond, params = sql('subject = "Vachana literature"')
	assert "tabRD Item Subject" in cond and params == ["%Vachana literature%"]
	cond, params = sql("date = 1880")
	assert cond == "year = %s" and params == [1880]
	with pytest.raises(sru.Diagnostic) as e:
		sql("date = soon")
	assert e.value.number == 36


def test_wildcards_in_the_query_are_literal():
	_cond, params = sql('title = "100%_sure"')
	assert params == ["%100\\%\\_sure%"] * 2


@pytest.mark.parametrize(
	"query,number",
	[
		("", 7),
		("title =", 10),
		("(title=a", 10),
		("title=a and", 10),
		("colour = red", 16),
		("title < 4", 10),
		("and title=a", 10),
		("title=a )", 10),
	],
)
def test_bad_queries_give_the_right_diagnostic(query, number):
	with pytest.raises(sru.Diagnostic) as e:
		sru.to_sql(sru.parse(query))
	assert e.value.number == number


def test_quoted_values_may_contain_operators_and_escaped_quotes():
	cond, params = sql('title = "war and peace"')
	assert params[0] == "%war and peace%"
	cond, params = sql('title = "say \\"hi\\""')
	assert params[0] == '%say "hi"%'


def test_search_response_carries_records_positions_and_the_next_page():
	xml = sru.search_response(
		total=25,
		records=["<record>1</record>", "<record>2</record>"],
		schema="marcxml",
		start=11,
		next_start=13,
		query="title=x",
		maximum=2,
	)
	root = ET.fromstring(xml)
	assert root.find("s:numberOfRecords", NS).text == "25"
	positions = [e.text for e in root.iter(f"{{{sru.SRU_NS}}}recordPosition")]
	assert positions == ["11", "12"]
	assert root.find("s:nextRecordPosition", NS).text == "13"
	assert root.find("s:records/s:record/s:recordSchema", NS).text == "info:srw/schema/1/marcxml-v1.1"


def test_a_diagnostic_response_is_a_200_style_document():
	root = ET.fromstring(sru.diagnostics_response("searchRetrieve", [sru.Diagnostic(16, "colour")]))
	assert root.find("s:numberOfRecords", NS).text == "0"
	text = ET.tostring(root, encoding="unicode")
	assert "info:srw/diagnostic/1/16" in text and "colour" in text
	root = ET.fromstring(sru.diagnostics_response("explain", [sru.Diagnostic(6, "x")]))
	assert root.tag.endswith("explainResponse")


def test_explain_names_the_server_indexes_and_schemas():
	xml = sru.explain_response(host="lib.example.org", port="443", database="sru", title="Lib & Co")
	root = ET.fromstring(xml)
	text = ET.tostring(root, encoding="unicode")
	assert "lib.example.org" in text and "Lib &amp; Co" in text
	for index in sru.EXPLAIN_INDEXES:
		assert f"<title>{index}</title>" in text or f">{index}<" in text
	assert "marcxml-v1.1" in text and "dc-v1.1" in text


def test_clamp():
	assert sru.clamp("5", 10, 50) == 5
	assert sru.clamp("999", 10, 50) == 50
	assert sru.clamp("x", 10, 50) == 10
	assert sru.clamp("0", 1, 100, minimum=1) == 1
