"""A language model's reply, read and refused where the page does not support it (pure rules)."""

from sok_resdesk.core import llm

PAGES = [
	{"leaf": 0, "text": "A HISTORY OF THE DECCAN"},
	{"leaf": 1, "text": "Printed for\nSahitya Akademi\nFirst published 1950\nISBN 978-0-306-40615-7"},
]


def test_reply_is_found_in_prose_and_fences():
	assert llm.parse_json('Sure!\n```json\n{"year": "1950"}\n```') == {"year": "1950"}
	assert llm.parse_json("no json here") is None
	assert llm.reply_text({"choices": [{"message": {"content": "hi"}}]}) == "hi"
	assert llm.reply_text({"error": "x"}) == ""


def test_supported_values_are_kept_with_where_they_were_printed():
	reply = '{"publisher": "Sahitya Akademi", "year": "1950", "isbn": "978-0-306-40615-7", "place": null}'
	got = {d["field"]: d for d in llm.front_details(reply, PAGES, {})}
	assert set(got) == {"publisher", "year", "isbn"}
	assert got["publisher"]["leaf"] == 1 and got["publisher"]["snippet"] == "Sahitya Akademi"


def test_guesses_are_dropped():
	reply = '{"publisher": "Oxford University Press", "year": "1951", "isbn": "978-0-306-40615-8", "place": "Pune"}'
	assert llm.front_details(reply, PAGES, {}) == []  # none of it is printed, and the ISBN fails its check
	assert llm.front_details('{"year": "1950"}', PAGES, {"year": 1950}) == []  # not new


def test_prompt_asks_only_for_what_is_missing_and_is_capped():
	system, user = llm.front_prompt([{"leaf": 0, "text": "x" * 20000}], ["year", "isbn"])
	assert "keys: year, isbn." in system
	assert len(user) == llm.MAX_PAGE_CHARS


CONTENTS = "CONTENTS\nPreface v\n1. Introduction 1\n2. The Early Dynasties 14"


def test_contents_entries_the_pages_support_are_kept():
	reply = (
		'{"entries": [{"title": "Preface", "page": "v"}, {"title": "1. Introduction", "page": "1", "level": 1},'
		' {"title": "The Early Dynasties", "page": "೧೪", "level": 9}, {"title": "Invented Chapter", "page": "50"},'
		' {"title": "Introduction", "page": "x?"}]}'
	)
	got = llm.contents_entries(reply, CONTENTS)
	assert [(e["title"], e["page"], e["level"]) for e in got] == [
		("Preface", "v", 1),
		("1. Introduction", "1", 1),
		("The Early Dynasties", "14", 4),
	]
	assert llm.contents_entries("not json", CONTENTS) == []
	assert llm.contents_entries('{"entries": "x"}', CONTENTS) == []


TYPES = ["Book", "Periodical", "Manuscript", "Other"]


def test_description_offers_only_what_is_new_and_sensible():
	reply = (
		'{"subjects": ["Vachana literature", "Basavanna", "basavanna", "Karnataka; history", "x"], '
		'"summary": "A study of the Vachana poets of twelfth-century Karnataka and their social message.", '
		'"item_type": "Manuscript"}'
	)
	got = {
		d["field"]: d
		for d in llm.describe_details(reply, {"subjects": "Basavanna", "item_type": "Book"}, TYPES)
	}
	assert (
		got["subjects"]["value"] == "Vachana literature; Karnataka history"
	)  # not the one it has, no repeats
	assert got["summary"]["value"].startswith("A study") and got["item_type"]["value"] == "Manuscript"
	assert got["subjects"]["leaf"] is None and got["subjects"]["confidence"] < 0.5


def test_description_keeps_what_the_book_has_and_refuses_odd_types():
	reply = '{"subjects": [], "summary": "A study of the Vachana poets of twelfth-century Karnataka.", "item_type": "Pamphlet"}'
	assert llm.describe_details(reply, {"summary": "Already described."}, TYPES) == []
	assert llm.describe_details("nothing", {}, TYPES) == []


def test_a_sentence_becomes_words_and_filters_the_library_has():
	q = "Kannada books by Kuvempu from the 1950s"
	reply = (
		'{"query": "Kuvempu", "language": "kannada", "year_from": 1950, "year_to": 1959, "item_type": "Book"}'
	)
	got = llm.understand_result(reply, q, ["Kannada", "Hindi"], TYPES, 2026)
	assert got == {
		"q": "Kuvempu",
		"filters": {"language_label": ["Kannada"], "item_type": ["Book"], "year_from": 1950, "year_to": 1959},
	}


def test_invented_words_unknown_languages_and_odd_years_are_refused():
	q = "old Kannada poems before 1900"
	assert (
		llm.understand_result('{"query": "Vachana", "language": "Kannada"}', q, ["Kannada"], TYPES, 2026)
		is None
	)
	got = llm.understand_result(
		'{"query": "poems", "language": "Klingon", "year_from": 1900, "year_to": 1800}',
		q,
		["Kannada"],
		TYPES,
		2026,
	)
	assert got is None  # nothing usable was found besides the words
	assert llm.understand_result("nothing", q, ["Kannada"], TYPES, 2026) is None
	ok = llm.understand_result('{"query": "poems", "year_to": 1900}', q, ["Kannada"], TYPES, 2026)
	assert ok == {"q": "poems", "filters": {"year_to": 1900}}
