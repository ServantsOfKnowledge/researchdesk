"""Annotations core (core/annotations.py): anchoring, W3C JSON-LD and exports. Pure Python."""

import csv
import io

import pytest

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
	assert w["body"][-1] == {
		"type": "SpecificResource",
		"source": "https://www.wikidata.org/wiki/Q1352279",
		"purpose": "identifying",
	}
	# what the passage is about: the Wikidata item, once, as linked data names it
	about = an.to_w3c({**note, "entity": "Q1352279"}, "p")
	assert [b.get("source") for b in about["body"] if b.get("type") == "SpecificResource"] == [
		"http://www.wikidata.org/entity/Q1352279"
	]
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


def test_leaf_of_a_target():
	assert an.leaf_of("https://lib.example/library/item/x?page=12&view=text") == 12
	assert an.leaf_of("https://lib.example/ark:/12345/r7b2/n7") == 7
	assert an.leaf_of("https://archive.org/details/x/page/n3") == 3
	assert an.leaf_of("https://archive.org/download/x/page/n4.jpg") == 4
	assert an.leaf_of("https://lib.example/library/item/x") is None


def test_a_web_annotation_from_another_tool_becomes_a_note():
	note = an.from_w3c(
		{
			"@context": "http://www.w3.org/ns/anno.jsonld",
			"type": "Annotation",
			"motivation": "commenting",
			"body": [
				{
					"type": "TextualBody",
					"value": "Same verse as in the 1890 edition",
					"purpose": "commenting",
				},
				{"type": "TextualBody", "value": "haridasa", "purpose": "tagging"},
				{
					"type": "SpecificResource",
					"source": "http://www.wikidata.org/entity/Q2724213",
					"purpose": "identifying",
				},
				"https://example.org/edition-1890",
			],
			"target": {
				"source": "https://lib.example/library/item/x?page=5&view=text",
				"selector": [
					{"type": "TextQuoteSelector", "exact": "Udupi", "prefix": "of ", "suffix": " Krishna"},
					{"type": "TextPositionSelector", "start": 42, "end": 47},
				],
			},
		}
	)
	assert note["kind"] == "Comment" and note["leaf"] == 5 and note["entity"] == "Q2724213"
	assert note["body"] == "Same verse as in the 1890 edition" and note["tags"] == "haridasa"
	assert note["link"] == "https://example.org/edition-1890"
	assert (note["exact"], note["start"], note["end"]) == ("Udupi", 42, 47)
	region = an.from_w3c(
		{
			"type": "Annotation",
			"motivation": "highlighting",
			"target": {
				"source": "https://archive.org/download/x/page/n2.jpg",
				"selector": {"type": "FragmentSelector", "value": "xywh=percent:10,10,20,20"},
			},
		}
	)
	assert region["kind"] == "Highlight" and region["region"] == "xywh=percent:10,10,20,20"


@pytest.mark.parametrize(
	"bad",
	[
		{"type": "Note"},
		{"type": "Annotation"},
		{"type": "Annotation", "target": "https://lib.example/library/item/x"},
		{"type": "Annotation", "target": {"source": "https://lib.example/library/item/x?page=1"}},
		{
			"type": "Annotation",
			"target": {"source": "x?page=1", "selector": {"type": "FragmentSelector", "value": "t=1"}},
		},
	],
)
def test_annotations_that_cannot_be_notes_say_why(bad):
	with pytest.raises(an.AnnotationError):
		an.from_w3c(bad)


def test_a_round_trip_keeps_the_note():
	w = an.to_w3c(
		{"kind": "Tag", "tags": "a, b", "entity": "Q1", "exact": "x", "start": 1, "end": 2},
		"https://lib.example/library/item/x?page=9&view=text",
	)
	back = an.from_w3c(w)
	assert (back["kind"], back["tags"], back["entity"], back["leaf"], back["exact"]) == (
		"Tag",
		"a, b",
		"Q1",
		9,
		"x",
	)


def test_collection_pages():
	c = an.collection("https://l/c/", "Notes", 250, 100)
	assert c["type"] == ["BasicContainer", "AnnotationCollection"] and c["total"] == 250
	assert c["first"].endswith("?page=0") and c["last"].endswith("?page=2")
	p = an.collection_page([{"id": "a"}], "https://l/c/", 1, 250, 100, embed=False)
	assert p["items"] == ["a"] and p["startIndex"] == 100 and p["partOf"]["total"] == 250
	assert p["next"].endswith("?page=2&iris=1") and p["prev"].endswith("?page=0&iris=1")
	assert "first" not in an.collection("https://l/c/", "Notes", 0, 100)
