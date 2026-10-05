"""Harvesting OAI-PMH repositories (core/harvest.py) and reading PDFs' text (core/pdftext.py).
Pure Python: the repository is stood in for by recorded answers."""

import pytest

from sok_resdesk.core import harvest, pdftext
from sok_resdesk.tests.oai_fixtures import HEAD, PAGE1, PAGE2, Resp, Session, make_pdf


def harvester(*answers):
	s = Session([a if isinstance(a, Resp) else Resp(a) for a in answers])
	return harvest.Harvester(
		"https://repo.example.org/oai/request", session=s, delay=0, sleep=lambda _s: None
	), s


def test_records_follow_resumption_tokens_and_mark_deleted():
	h, s = harvester(PAGE1, PAGE2)
	recs = list(h.records("oai_dc", "col_1", "2024-01-01"))
	assert [r["identifier"].rsplit("/", 1)[1] for r in recs] == ["42", "43", "7"]
	assert recs[2]["deleted"] and not recs[0]["deleted"]
	assert recs[0]["sets"] == ["col_1"]
	assert s.asked[0] == {
		"verb": "ListRecords",
		"metadataPrefix": "oai_dc",
		"set": "col_1",
		"from": "2024-01-01",
	}
	assert s.asked[1] == {"verb": "ListRecords", "resumptionToken": "tok1"}


def test_waits_when_asked_and_reports_errors():
	busy = Resp("", 503, {"Retry-After": "2"})
	empty = HEAD + '<error code="noRecordsMatch">none</error></OAI-PMH>'
	h, s = harvester(busy, empty)
	assert list(h.records()) == []  # waited, then nothing to harvest
	h, _s = harvester(HEAD + '<error code="badArgument">no such set</error></OAI-PMH>')
	with pytest.raises(harvest.HarvestError, match="badArgument"):
		list(h.records(set_spec="nope"))
	with pytest.raises(harvest.HarvestError):
		harvest.Harvester("ftp://x")


def test_count_from_complete_list_size():
	page = (
		HEAD
		+ '<ListIdentifiers><header><identifier>a</identifier></header><resumptionToken completeListSize="1234">t</resumptionToken></ListIdentifiers></OAI-PMH>'
	)
	h, _s = harvester(page)
	assert h.count() == 1234


def test_a_record_becomes_a_catalogue_entry():
	h, _s = harvester(PAGE1, PAGE2)
	rec = next(h.records())
	meta = harvest.to_meta(rec, "Example University Repository")
	assert meta["title"] == ["ಕನ್ನಡ ಸಾಹಿತ್ಯ ಚರಿತ್ರೆ"]
	assert meta["alt_title"] == "History of Kannada literature"
	assert meta["date"] == "1953"  # the year of publication, not the day it was deposited
	assert meta["licenseurl"] == "http://creativecommons.org/licenses/by/4.0/"
	assert meta["rights"] == "Open access"
	assert meta["collection"] == ["Example University Repository"]
	found = harvest.links(rec["dc"])
	assert found == {
		"landing": "http://hdl.handle.net/123456789/42",
		"pdf": "https://repo.example.org/bitstream/123456789/42/1/book.pdf",
	}
	# a bare DOI is a landing page too
	assert harvest.links({"identifier": ["10.5555/xyz"]})["landing"] == "https://doi.org/10.5555/xyz"


def test_identifiers_are_stable_and_safe():
	assert harvest.item_id_for("oai:repo.example.org:123456789/42", "kud") == "kud-123456789-42"
	assert harvest.item_id_for("oai:eprints.example.org:5", "ep") == "ep-5"
	long = harvest.item_id_for("oai:x:" + "a" * 200, "kud")
	assert len(long) <= 100 and long == harvest.item_id_for("oai:x:" + "a" * 200, "kud")


def test_pdf_found_on_the_landing_page():
	page = '<html><head><meta name="citation_pdf_url" content="/bitstreams/9/download"></head></html>'
	assert (
		harvest.pdf_from_landing(page, "https://repo.example.org/items/1")
		== "https://repo.example.org/bitstreams/9/download"
	)
	page = '<a href="files/thesis.pdf">Download</a>'
	assert (
		harvest.pdf_from_landing(page, "https://ep.example.org/5/")
		== "https://ep.example.org/5/files/thesis.pdf"
	)
	assert harvest.pdf_from_landing("<p>nothing</p>", "https://x/") == ""


def test_pdf_text_layer_page_by_page():
	pages = pdftext.pages_from_pdf(
		make_pdf(["The first page of the book text", "Second page, with more text"])
	)
	assert [p["leaf"] for p in pages] == [0, 1]
	assert pages[0]["text"] == "The first page of the book text"
	assert pdftext.has_text_layer(pages)
	# a scan with no text: no text layer
	assert not pdftext.has_text_layer(pdftext.pages_from_pdf(make_pdf(["", "", "x"])))
	assert pdftext.tidy("hyphen-\nated  word\n\n\n\nnext") == "hyphenated word\n\nnext"
