"""Wikidata items on notes (core/wikidata.py): Q-numbers, search answers, the language to search in."""

from urllib.parse import parse_qs, urlparse

import pytest

from sok_resdesk.core import wikidata as wd


@pytest.mark.parametrize(
	"value, q",
	[
		("Q2724213", "Q2724213"),
		("q42", "Q42"),
		("wd:Q42", "Q42"),
		("https://www.wikidata.org/wiki/Q42", "Q42"),
		("http://www.wikidata.org/entity/Q42", "Q42"),
		("https://m.wikidata.org/wiki/Q42#P31", "Q42"),
		("https://example.org/Q42", None),
		("Q0", None),
		("Q42x", None),
		("Purandara Dasa", None),
		("", None),
		(None, None),
	],
)
def test_qid(value, q):
	assert wd.qid(value) == q


def test_uris():
	assert wd.entity_uri("Q42") == "http://www.wikidata.org/entity/Q42"
	assert wd.page_url("Q42") == "https://www.wikidata.org/wiki/Q42"


def test_search_in_the_script_typed():
	assert wd.search_language("ಪುರಂದರ") == "kn"
	assert wd.search_language("पुरंदर") == "hi"
	assert wd.search_language("புரந்தர") == "ta"
	assert wd.search_language("Purandara", "en") == "en"
	q = parse_qs(urlparse(wd.search_url("ಪುರಂದರ", "kn", limit=99)).query)
	assert q["action"] == ["wbsearchentities"] and q["language"] == ["kn"] and q["limit"] == ["20"]


def test_parse_answers():
	hits = wd.parse_search(
		{
			"search": [
				{"id": "Q2724213", "label": "Purandara Dasa", "description": "Carnatic composer"},
				{"id": "P31"},
			]
		}
	)
	assert hits == [{"id": "Q2724213", "label": "Purandara Dasa", "description": "Carnatic composer"}]
	ents = wd.parse_entities(
		{
			"entities": {
				"Q1": {"labels": {"en": {"value": "Udupi"}, "kn": {"value": "ಉಡುಪಿ"}}, "descriptions": {}},
				"Q2": {"missing": ""},
			}
		},
		"kn",
	)
	assert ents == {"Q1": {"label": "ಉಡುಪಿ", "description": ""}}
