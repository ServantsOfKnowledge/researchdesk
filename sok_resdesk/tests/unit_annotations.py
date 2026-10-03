"""Annotations core (core/annotations.py): anchoring, W3C JSON-LD and exports. Pure Python."""

import csv
import io

from sok_resdesk.core import annotations as an

TEXT = "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು. Kanakadasa sang of Udupi; Udupi Krishna faced him."


def test_a_passage_keeps_its_place_and_finds_it_again_after_corrections():
	start = TEXT.index("Udupi Krishna")
	end = start + len("Udupi")
	q = an.quote_selector(TEXT, start, end)
	assert q["exact"] == "Udupi" and q["suffix"].startswith(" Krishna")
	assert an.anchor(TEXT, start, end, **q) == (start, end)
	# OCR corrected earlier on the page: positions move, the quote and its context find it again,
	# and the second "Udupi" (with " Krishna" after it) is chosen over the first
	fixed = TEXT.replace("ಕೀರ್ತನೆಗಳು.", "ಕೀರ್ತನೆಗಳು,  ")
	s, e = an.anchor(fixed, start, end, **q)
	assert fixed[s:e] == "Udupi" and fixed[e : e + 8] == " Krishna"
	# the words are gone: detached
	assert an.anchor("nothing here", start, end, **q) is None
	assert an.anchor(TEXT, 0, 0, "") is None


def test_regions_are_percent_rectangles():
	assert an.region(10, 20.5, 30, 40) == "xywh=percent:10,20.5,30,40"
	assert an.region(-5, 90, 50, 50) == "xywh=percent:0,90,50,10"  # kept on the page
	assert an.parse_region("xywh=percent:10,20.5,30,40") == (10, 20.5, 30, 40)
	assert an.parse_region("xywh=1,2,3,4") is None


def test_w3c_annotation():
	note = {
		"id": "https://lib.example/api/method/sok_resdesk.annotations.get?name=a1",
		"kind": "Comment",
		"body": "Compare with the 1890 edition",
		"tags": "udupi, krishna, udupi",
		"link": "https://www.wikidata.org/wiki/Q1352279",
		"exact": "Udupi",
		"prefix": "of ",
		"suffix": " Krishna",
		"start": 42,
		"end": 47,
		"creator": "A Reader",
	}
	w = an.to_w3c(note, "https://lib.example/library/item/x?page=5&view=text")
	assert w["@context"] == "http://www.w3.org/ns/anno.jsonld" and w["type"] == "Annotation"
	assert w["motivation"] == "commenting"
	kinds = {s["type"] for s in w["target"]["selector"]}
	assert kinds == {"TextQuoteSelector", "TextPositionSelector"}
	purposes = [b["purpose"] for b in w["body"]]
	assert purposes == ["commenting", "tagging", "tagging", "identifying"]  # tags de-duplicated
	r = an.to_w3c({"kind": "Highlight", "region": "xywh=percent:1,2,3,4"}, "p", image_url="img.jpg")
	assert r["motivation"] == "highlighting" and r["target"]["source"] == "img.jpg"
	assert r["target"]["selector"]["type"] == "FragmentSelector" and "body" not in r
	assert an.to_w3c({"kind": "OCR error", "exact": "x"}, "p")["motivation"] == "editing"
	page = an.page_collection([w], "c1")
	assert page["type"] == "AnnotationPage" and page["items"] == [w]


def test_exports():
	notes = [
		{
			"book_title": "Book A",
			"book_citation": "A. (1950). Book A.",
			"page": "p. 3",
			"kind": "Comment",
			"exact": "Udupi",
			"body": "see map",
			"tags": "place",
			"url": "https://l/x?page=5&view=text",
		},
		{"book_title": "Book A", "page": "leaf 9", "kind": "Highlight", "region": "xywh=percent:1,2,3,4"},
		{"book_title": "Book B", "page": "p. 1", "kind": "Question", "body": "Who printed this?"},
	]
	md = an.to_markdown(notes)
	assert (
		md.count("## ") == 2 and "**p. 3** “Udupi”: see map #place [p. 3](https://l/x?page=5&view=text)" in md
	)
	assert "(a region of the page image)" in md
	rows = list(csv.reader(io.StringIO(an.to_csv(notes))))
	assert rows[0] == list(an.CSV_COLUMNS) and rows[2][3] == "(region)" and len(rows) == 4
	assert an.split_tags(["a", " b ", "a", ""]) == ["a", "b"]
