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
