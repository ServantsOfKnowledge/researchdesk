"""Giving back to Wikidata and the Library of Congress (core/contribute.py); book items naming
matched authors (core/push.py). Pure Python."""

from sok_resdesk.core import contribute as c
from sok_resdesk.core import push

PERSON = {"labels": {"en": "Kanakadasa"}, "aliases": {"en": ["Kanaka Dasa"]}}


def test_names_in_the_books_scripts_are_offered():
	edits = c.name_edits(
		"Q1", PERSON, [("ಕನಕದಾಸ", "kn"), ("ಕನಕದಾಸರು", "kn"), ("Kanakadasa", "en"), ("ಕನಕದಾಸ", "kn")]
	)
	assert edits == [
		{"qid": "Q1", "kind": "label", "lang": "kn", "value": "ಕನಕದಾಸ"},
		{"qid": "Q1", "kind": "alias", "lang": "kn", "value": "ಕನಕದಾಸರು"},
	]
	# already there: nothing to add
	assert c.name_edits("Q1", {"labels": {"kn": "ಕನಕದಾಸ"}}, [("ಕನಕದಾಸ", "kn")]) == []
	# Devanagari in a Marathi book is Marathi; in an unknown one, Hindi
	assert c.name_language("संत तुकाराम", "mr") == "mr"
	assert c.name_language("संत तुकाराम", "") == "hi"
	assert c.name_language("Tukaram", "mr") is None


def test_authors_linked_on_book_items():
	claims = {"P50": [{"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}}]}
	authors = [
		{"qid": "Q2", "name": "A", "ordinal": 1},
		{"qid": "Q3", "name": "ಬಿ", "ordinal": 2},
		{"qid": "", "name": "C", "ordinal": 3},
	]
	assert c.author_edits("Q9", claims, authors) == [
		{"qid": "Q9", "kind": "author", "person": "Q3", "value": "ಬಿ", "ordinal": 2}
	]


def test_quickstatements_and_api_data():
	edits = [
		{"qid": "Q1", "kind": "label", "lang": "kn", "value": "ಕನಕದಾಸ"},
		{"qid": "Q1", "kind": "alias", "lang": "kn", "value": 'say "hi"'},
		{
			"qid": "Q9",
			"kind": "author",
			"person": "Q1",
			"value": "ಕನಕದಾಸ",
			"ordinal": 1,
			"source_url": "https://lib/x",
		},
	]
	qs = c.quickstatements(edits).splitlines()
	assert qs[0] == 'Q1\tLkn\t"ಕನಕದಾಸ"'
	assert qs[1] == "Q1\tAkn\t\"say 'hi'\""
	assert qs[2] == 'Q9\tP50\tQ1\tP1932\t"ಕನಕದಾಸ"\tP1545\t"1"\tS854\t"https://lib/x"'
	data = c.wbeditentity_data(edits)
	assert data["labels"]["kn"]["value"] == "ಕನಕದಾಸ"
	assert data["aliases"][0] == {"language": "kn", "value": 'say "hi"', "add": ""}
	claim = data["claims"][0]
	assert claim["mainsnak"]["datavalue"]["value"]["id"] == "Q1"
	assert claim["qualifiers"]["P1932"][0]["datavalue"]["value"] == "ಕನಕದಾಸ"
	assert claim["references"][0]["snaks"]["P854"][0]["datavalue"]["value"] == "https://lib/x"


def test_saco_list():
	text = c.saco_csv(
		[
			{
				"subject": "Haridasa literature",
				"books": 12,
				"titles": ["A", "B"],
				"url": "https://lib/?subjects=x",
			}
		]
	)
	assert text.splitlines()[0] == "subject,books,example titles,portal search,candidates looked at"
	assert "Haridasa literature,12,A | B" in text


def test_book_items_name_matched_authors_as_people():
	record = {
		"item_id": "x",
		"title": "ಕೀರ್ತನೆಗಳು",
		"language": "kan",
		"creators": ["ಕನಕದಾಸ", "Someone"],
		"creator_ids": [{"wikidata": "Q1", "viaf": ""}, {}],
	}
	claims = push.wikidata_entity(record)["claims"]
	p50 = [x for x in claims if x["mainsnak"]["property"] == "P50"]
	p2093 = [x for x in claims if x["mainsnak"]["property"] == "P2093"]
	assert p50[0]["mainsnak"]["datavalue"]["value"]["id"] == "Q1"
	assert p50[0]["qualifiers"]["P1932"][0]["datavalue"]["value"] == "ಕನಕದಾಸ"
	assert [x["mainsnak"]["datavalue"]["value"] for x in p2093] == ["Someone"]
