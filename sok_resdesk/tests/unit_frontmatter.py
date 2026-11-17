"""Details read from a title page and an imprint page (pure rules)."""

from sok_resdesk.core import frontmatter as fm

PAGES = [
	{"leaf": 0, "text": "A HISTORY OF THE DECCAN\nBy R. Narasimhachar"},
	{
		"leaf": 1,
		"text": "First published 1950\nPublished by Sahitya Akademi, New Delhi\nISBN 978-0-306-40615-7\nAll rights reserved",
	},
]


def by_field(pages):
	return {f["field"]: f for f in fm.read(pages)}


def test_labelled_details_are_found_with_their_page():
	got = by_field(PAGES)
	assert got["publisher"]["value"] == "Sahitya Akademi"
	assert got["place"]["value"] == "New Delhi"
	assert got["year"]["value"] == "1950"
	assert got["isbn"]["value"] == "978-0-306-40615-7"
	assert got["year"]["leaf"] == 1 and "1950" in got["year"]["snippet"]


def test_isbn_check_digit():
	assert fm.valid_isbn("0-306-40615-2") and fm.valid_isbn("978-0-306-40615-7")
	assert not fm.valid_isbn("978-0-306-40615-8")
	assert not fm.read([{"leaf": 0, "text": "ISBN 978-0-306-40615-8"}])


def test_indic_labels_and_digits():
	got = by_field([{"leaf": 1, "text": "ಪ್ರಕಾಶಕರು: ಕನ್ನಡ ಸಾಹಿತ್ಯ ಪರಿಷತ್ತು, ಬೆಂಗಳೂರು\nಪ್ರಥಮ ಮುದ್ರಣ ೧೯೬೨"}])
	assert got["publisher"]["value"] == "ಕನ್ನಡ ಸಾಹಿತ್ಯ ಪರಿಷತ್ತು"
	assert got["place"]["value"] == "ಬೆಂಗಳೂರು"
	assert got["year"]["value"] == "1962"


def test_label_alone_takes_the_next_line_and_noise_is_refused():
	assert by_field([{"leaf": 1, "text": "Publisher\nOxford University Press"}])["publisher"]["value"] == (
		"Oxford University Press"
	)
	assert not fm.read([{"leaf": 1, "text": "Copyright 1850000 all rights reserved"}])  # no such year
	assert (
		fm.read([{"leaf": 0, "text": ""}] * 12 + [{"leaf": 20, "text": "Published by Somebody"}]) == []
	)  # past the front


def test_only_what_is_new_is_offered():
	assert fm.is_new("publisher", "Oxford University Press", "")
	assert not fm.is_new("publisher", "Oxford University Press", "Oxford University Press, Delhi")
	assert not fm.is_new("year", "1950", 1950)
	assert fm.is_new("year", "1951", 1950)
