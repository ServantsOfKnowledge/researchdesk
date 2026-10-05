"""Wikisource wikitext, names and the API client (no Frappe, no network)."""

import pytest

from sok_resdesk.core import wikisource as ws
from sok_resdesk.tests import wikisource_fixtures as fx
from sok_resdesk.tests.wikisource_fixtures import Session


def test_a_page_text_is_plain_and_has_its_quality():
	page = ws.parse_page(fx.PAGE_VALIDATED)
	assert page["quality"] == 4 and page["user"] == "Volunteer"
	# header and footer (noinclude) gone, {{larger}} unwrapped, other templates and notes dropped,
	# links give their label, bold marks removed
	assert page["text"] == "ಮೊದಲ ಪುಟ\n\nಕನಕದಾಸ ಹೇಳಿದ ಹರಿಯ ಮಹಿಮೆ."
	assert ws.parse_page(fx.PAGE_PROOFREAD) == {"quality": 3, "user": "Reader", "text": "ಎರಡನೇ ಪುಟ"}
	assert ws.parse_page(fx.PAGE_BLANK)["text"] == "" and ws.parse_page("no tag at all")["quality"] == 0


def test_plain_handles_markup_without_losing_words():
	assert ws.plain("A '''bold''' and ''italic'' word<br/>next [http://x.org a site] <!-- c -->") == (
		"A bold and italic word\nnext a site"
	)
	assert ws.plain("{{sc|Small caps}} {{unknown|gone}} [[File:x.jpg|thumb]]{{c|{{larger|nested}}}}") == (
		"Small caps  nested"
	)
	assert ws.plain("") == ""


def test_the_index_fields():
	f = ws.parse_index(fx.INDEX)
	assert f["title"] == "ಕನಕದಾಸ ಕೀರ್ತನೆಗಳು"  # the link inside kept as its label
	assert f["author"] == "Kanakadasa; Other Poet" and f["year"] == "1931" and f["language"] == "kn"
	assert f["publisher"] == "Mysore Press" and f["source"] == "pdf"
	assert "volume" not in f and "isbn" not in f  # empty fields are left out


def test_catalogue_metadata_from_an_index():
	m = ws.meta(
		ws.parse_index(fx.INDEX), site="kn.wikisource.org", index_title="Index:Kanaka.pdf", pages=5, scan="x"
	)
	assert m["title"] == ["ಕನಕದಾಸ ಕೀರ್ತನೆಗಳು"] and m["creator"] == ["Kanakadasa", "Other Poet"]
	assert m["language"] == ["kn"] and m["date"] == "1931" and m["licenseurl"] == ws.LICENCE
	assert "CC BY-SA" in m["rights"]
	bare = ws.meta({}, site="sa.wikisource.org", index_title="Index:Some book.djvu", pages=0, scan="")
	assert bare["title"] == ["Some book"] and bare["language"] == ["sa"] and "creator" not in bare


def test_names_and_addresses():
	assert ws.item_id_for("kn.wikisource.org", "Index:Kanaka.pdf") == "ws-kn-Kanaka.pdf"
	assert ws.item_id_for("kn.wikisource.org", "Index:ಕನಕ.pdf") == "ws-kn-ಕನಕ.pdf"
	assert ws.page_number("Page:Kanaka.pdf/12", "Kanaka.pdf") == 12
	assert ws.page_number("Page:Other.pdf/12", "Kanaka.pdf") is None
	assert ws.page_number("Page:Kanaka.pdf/note", "Kanaka.pdf") is None
	assert ws.image_url("kn.wikisource.org", "Some book.pdf", 0) == (
		"https://kn.wikisource.org/wiki/Special:Redirect/file/Some_book.pdf?page=1&width=1000"
	)
	assert ws.index_url("kn.wikisource.org", "Index:Some book.pdf").endswith("/wiki/Index:Some_book.pdf")


@pytest.mark.parametrize(
	"site", ["kn.wikisource.org", "wikisource.org", "https://sa.wikisource.org/", "SA.WikiSource.org"]
)
def test_client_accepts_wikisource_addresses(site):
	assert ws.WikiClient(site).api.endswith("/w/api.php")


@pytest.mark.parametrize(
	"site", ["example.org", "kn.wikipedia.org", "localhost", "evil.org/wikisource.org", ""]
)
def test_client_refuses_any_other_site(site):
	with pytest.raises(ws.WikiError):
		ws.WikiClient(site)


def client(*answers):
	return ws.WikiClient("kn.wikisource.org", delay=0, session=Session(*answers))


def test_the_client_reads_a_book():
	c = client(fx.SITEINFO)
	assert c.namespaces() == (252, 250)
	assert list(client(fx.CATEGORY).indexes_in_category("Books")) == [
		"Index:Kanaka.pdf",
		"Index:Other book.djvu",
	]
	assert "Kanakadasa" in client(fx.INDEX_API).wikitext("Index:Kanaka.pdf")
	assert client(fx.FILEINFO).file_pages("Kanaka.pdf") == 5
	pages = list(client(fx.PAGES).pages("Kanaka.pdf"))
	assert [(p["leaf"], p["quality"]) for p in pages] == [(0, 4), (1, 3), (2, 1), (3, 0)]  # /note is no page


def test_the_client_follows_continuation_and_reports_errors():
	first = {**fx.PAGES, "continue": {"gapcontinue": "Kanaka.pdf/5", "continue": "gapcontinue||"}}
	more = fx.api_pages({"Page:Kanaka.pdf/5": fx.PAGE_PROOFREAD})
	c = client(first, more)
	assert [p["leaf"] for p in c.pages("Kanaka.pdf")] == [0, 1, 2, 3, 4]
	assert c.session.asked[1]["gapcontinue"] == "Kanaka.pdf/5"
	with pytest.raises(ws.WikiError, match="is not on"):
		client({"query": {"pages": [{"title": "Index:X", "missing": True}]}}).wikitext("Index:X")
	with pytest.raises(ws.WikiError, match="Bad title"):
		client({"error": {"code": "badtitle", "info": "Bad title"}}).wikitext("x")
