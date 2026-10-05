"""The cataloguer's review queue: the checks (core/review.py). Pure Python."""

from sok_resdesk.core import review


def codes(record, **kw):
	return {f["code"] for f in review.check(record, this_year=2026, **kw)}


GOOD = {
	"item_id": "kanakadasa1950",
	"title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು",
	"year": 1950,
	"language": "kan",
	"creators": ["Kanakadasa"],
	"subjects": ["Haridasa"],
}


def test_a_good_record_has_nothing_to_review():
	assert codes(GOOD) == set()


def test_year():
	assert codes({**GOOD, "year": None, "date_raw": "[19--?]"}) == {"no_year"}
	assert (
		review.check({**GOOD, "year": None, "date_raw": "[19--?]"}, 2026)[0]["detail"]
		== "the record says “[19--?]”"
	)
	assert codes({**GOOD, "year": 2999}) == {"odd_year"}
	assert codes({**GOOD, "year": 1200}) == {"odd_year"}  # before printing


def test_language_and_script():
	assert codes({**GOOD, "language": "und"}) == {"no_language"}
	assert codes({**GOOD, "language": "eng", "language_label": "English"}) == {"language_script"}
	assert codes({**GOOD, "language": "san"}) == set()  # Sanskrit in Kannada script is fine
	assert (
		codes({**GOOD, "title": "History of Mysore", "language": "kan"}) == set()
	)  # Latin titles: no opinion
	assert codes({**GOOD, "title": "भगवद्गीता", "language": "kan"}) == {"language_script"}


def test_authors_titles_subjects():
	assert codes({**GOOD, "creators": []}) == {"no_creator"}
	assert codes({**GOOD, "creators": ["Unknown"]}) == {"odd_creator"}
	assert codes({**GOOD, "creators": ["Anon."]}) == {"odd_creator"}
	assert codes({**GOOD, "title": "kanakadasa1950"}) == {"odd_title"}  # the identifier as title
	assert codes({**GOOD, "title": "2015.123456.Kanaka_Dasa_Kirtanegalu"}) == {"odd_title"}
	assert codes({**GOOD, "title": "scan_0001_final.pdf"}) == {"odd_title"}
	assert codes({**GOOD, "title": "THE HISTORY OF MYSORE", "language": "eng"}) == {"odd_title"}
	assert codes({**GOOD, "subjects": []}) == {"no_subjects"}


def test_duplicates():
	recs = [
		{"item_id": "a", "title": "The History of Mysore", "creators": ["Rao, B."], "year": 1950},
		{"item_id": "b", "title": "History of Mysore.", "creators": ["Rao, B."], "year": None},
		{
			"item_id": "c",
			"title": "History of Mysore",
			"creators": ["Rao, B."],
			"year": 1970,
		},  # another edition
		{"item_id": "d", "title": "History of Mysore", "creators": ["Someone Else"], "year": 1950},
		{"item_id": "e", "title": "Ab", "creators": ["X"]},
		{"item_id": "f", "title": "Ab", "creators": ["X"]},  # too short to tell
	]
	d = review.duplicates(recs)
	assert d["a"] == ["b"]
	assert sorted(d["b"]) == ["a", "c"]
	assert d["c"] == ["b"]
	assert "d" not in d and "e" not in d


def test_vowel_signs_count_as_letters():
	# mostly Kannada, a few Latin letters: still a Kannada title
	assert review.script_block("ರಾಮಾಯಣ ದರ್ಶನಂ rdtest") == 0x0C80
	assert review.script_block("History of Mysore ಮೈಸೂರು") is None
