"""Table of contents: finding the contents pages, reading their lines, trusting the result, and the
page image each printed page is (core/contents.py)."""

from sok_resdesk.core import contents

ENGLISH = """CONTENTS

Preface ............ v
1. Introduction .......... 1
2. The Early Dynasties ....... 14
   2.1 The Kadambas ....... 15
3. Inscriptions and Their Makers
   in the Deccan ..... 42
Index ........ 310
"""

KANNADA = """ವಿಷಯ ಸೂಚಿ

ಪ್ರಸ್ತಾವನೆ ............ ೫
ವಚನ ಸಾಹಿತ್ಯದ ಹುಟ್ಟು ........ ೧೨
ಬಸವಣ್ಣನವರ ವಚನಗಳು ........ ೨೯
ಅಕ್ಕಮಹಾದೇವಿ ........ ೬೧
"""


def test_entries_are_read_with_their_pages_and_levels():
	got = contents.parse([ENGLISH])
	assert [(e["title"], e["page"], e["level"]) for e in got] == [
		("Preface", "v", 1),
		("1. Introduction", "1", 1),
		("2. The Early Dynasties", "14", 1),
		("2.1 The Kadambas", "15", 2),
		("3. Inscriptions and Their Makers in the Deccan", "42", 1),
		("Index", "310", 1),
	]


def test_a_title_wrapped_over_two_lines_is_joined():
	got = contents.parse([ENGLISH])
	assert any(e["title"].startswith("3. Inscriptions") and e["title"].endswith("Deccan") for e in got)


def test_kannada_digits_become_page_numbers():
	got = contents.parse([KANNADA])
	assert [e["page"] for e in got] == ["5", "12", "29", "61"]
	assert got[1]["title"] == "ವಚನ ಸಾಹಿತ್ಯದ ಹುಟ್ಟು"
	assert contents.digits("೧೨") == "12" and contents.digits("१२") == "12"


def test_the_contents_pages_are_found_by_their_heading_and_continue():
	pages = [{"leaf": 0, "text": "Title page"}, {"leaf": 1, "text": "Copyright 1950"}]
	pages += [
		{"leaf": 2, "text": ENGLISH},
		{"leaf": 3, "text": "4. More ...... 50\n5. Again ..... 60\n6. End ..... 70"},
	]
	pages += [{"leaf": 4, "text": "Chapter one begins here and goes on for a long while"}]
	found = contents.find_pages(pages)
	assert found == {"leaves": [2, 3], "heading": True}


def test_without_a_heading_the_page_that_is_all_entries_is_taken():
	pages = [
		{"leaf": 0, "text": "Title"},
		{"leaf": 1, "text": "\n".join(f"Chapter number {i} ...... {i * 10}" for i in range(1, 9))},
	]
	assert contents.find_pages(pages) == {"leaves": [1], "heading": False}
	assert contents.find_pages([{"leaf": 0, "text": "Just prose, no list at all."}]) == {
		"leaves": [],
		"heading": False,
	}


def test_a_garbled_list_is_called_unclear():
	entries = [{"title": "a b", "page": p, "level": 1} for p in ("40", "3", "99", "7")]
	assert contents.quality(entries, 8)["unclear"]
	assert contents.quality(contents.parse([ENGLISH]), 7)["unclear"] is False
	assert contents.quality([], 0)["why"] == "fewer than three entries"


def test_printed_pages_find_their_page_images():
	entries = [
		{"title": "1. Introduction", "page": "1", "level": 1},
		{"title": "Preface", "page": "v", "level": 1},
	]
	# by labels the book has
	got = contents.leaves_for(entries, {9: "1", 4: "v"}, {}, after=3)
	assert [e["leaf"] for e in got] == [9, 4]
	# else by where the first titles start after the contents pages: page 1 is image 9
	texts = {5: "Foreword", 9: "1. Introduction\nThe story begins"}
	got = contents.leaves_for(entries, {}, texts, after=3)
	assert got[0]["leaf"] == 9 and got[1]["leaf"] is None  # a roman page has no number to add the offset to
