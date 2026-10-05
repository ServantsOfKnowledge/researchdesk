"""Reading library systems' MARC (core/marcin.py) and matching it to books here (core/libmatch.py)."""

from sok_resdesk.core import libmatch, marcin
from sok_resdesk.tests.libsys_fixtures import KOHA_XML, iso2709


def test_marcxml_from_koha():
	recs = list(marcin.read(KOHA_XML.encode()))
	assert len(recs) == 2
	s = marcin.summary(recs[0])
	assert s["id"] == "4512"  # Koha's biblionumber
	assert s["title"] == "ವಚನ ಸಾಹಿತ್ಯ"  # the title in its own script first
	assert s["alt_title"] == "Vachana sahitya"
	assert s["creators"] == ["Halakatti, P. G"]
	assert (s["year"], s["language"], s["place"]) == ("1931", "kan", "Dharwad")
	assert s["publisher"] == "Karnatak Vidyavardhaka Sangha"
	assert s["subjects"] == ["Vachanas"]
	other = marcin.summary(recs[1])
	assert other["isbn"] == "9788172011234"
	assert other["archive_ids"] == ["rdtestlib-linked"]


def test_iso2709():
	data = iso2709(
		[
			("001", "77"),
			("245", "1", "0", [("a", "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು :"), ("b", "ಮೊದಲ ಭಾಗ")]),
			("100", "1", " ", [("a", "Kanakadasa")]),
		]
	) + iso2709([("001", "78"), ("245", "0", "0", [("a", "Second")])])
	recs = list(marcin.read(data))
	assert [marcin.record_id(r) for r in recs] == ["77", "78"]
	assert marcin.summary(recs[0])["title"] == "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು : ಮೊದಲ ಭಾಗ"


def test_links_are_added_once_and_the_record_kept():
	rec = next(marcin.read(KOHA_XML.encode()))
	out = marcin.with_links(
		rec,
		[("https://lib.example/library/item/x", "Read online"), ("https://lib.example/library/item/x", "")],
	)
	added = [f for f in out.data("856")]
	assert len(added) == 1 and added[0][1:3] == ("4", "1")
	assert out.fields[: len(rec.fields)] == rec.fields
	again = next(marcin.read(marcin.collection_xml([out]).encode()))
	assert marcin.links(again) == ["https://lib.example/library/item/x"]
	assert marcin.summary(again)["title"] == "ವಚನ ಸಾಹಿತ್ಯ"


def test_matching():
	rec = marcin.summary(next(marcin.read(KOHA_XML.encode())))
	same = {"item_id": "a", "title": "ವಚನ ಸಾಹಿತ್ಯ", "creators": ["Halakatti, P.G."], "year": 1931}
	romanised = {"item_id": "b", "title": "ಬೇರೆ", "alt_title": "Vachana Sahitya", "creators": [], "year": 1931}
	other = {"item_id": "c", "title": "Basava purana", "creators": ["Halakatti, P. G."], "year": 1931}
	ranked = libmatch.best(rec, [other, romanised, same])
	assert [r["item_id"] for r in ranked][:2] == ["a", "b"]
	assert ranked[0]["score"] >= libmatch.LINK_AT
	assert libmatch.score(rec, other)["score"] < libmatch.PROPOSE_AT  # same author, another book
	assert libmatch.decide(ranked) == "Proposed"  # two close candidates: a person decides
	assert libmatch.decide(ranked[:1] + ranked[2:]) == "Linked"
	assert libmatch.decide([]) == "No match"
	linked = marcin.summary(list(marcin.read(KOHA_XML.encode()))[1])
	assert libmatch.score(linked, {"item_id": "rdtestlib-linked"})["score"] == 1.0
	assert libmatch.score(linked, {"item_id": "z", "isbn": "978-81-7201-123-4"})["score"] == 0.98
