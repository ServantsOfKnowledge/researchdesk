"""DOIs from DataCite (core/datacite.py): DOI names and the metadata sent."""

import pytest

from sok_resdesk.core import datacite as dc

RECORD = {
	"item_id": "kanakadasa1950",
	"title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು",
	"alt_title": "Kanakadasara Kirtanegalu",
	"creators": ["Kanakadasa", "Rao, B. Venkoba"],
	"year": 1950,
	"language": "kan",
	"publisher": "Kannada Sahitya Parishat",
	"subjects": ["Haridasa"],
	"description": "Songs.",
	"licence_url": "https://creativecommons.org/publicdomain/mark/1.0/",
	"page_count": 120,
	"item_type": "Book",
	"persistent_id": "ark:/12345/r7b2",
	"source": "Internet Archive",
}


def test_doi_names():
	assert dc.doi_for("10.12345", "Kanakadasa1950", "rd.") == "10.12345/RD.KANAKADASA1950"
	assert dc.suffix_for("a b/c?d", "") == "a-b-c-d"
	for bad in ("", "11.1234", "10.12", "10.abcd"):
		with pytest.raises(dc.DataCiteError):
			dc.check_prefix(bad)


def test_attributes():
	a = dc.attributes(RECORD, "https://lib.example/ark:/12345/r7b2", "SOK Research Desk", 2026)
	assert a["publisher"] == {"name": "SOK Research Desk"} and a["publicationYear"] == 1950
	assert a["types"] == {"resourceTypeGeneral": "Book", "resourceType": "Book"}
	assert a["creators"][1] == {
		"name": "Rao, B. Venkoba",
		"nameType": "Personal",
		"givenName": "B. Venkoba",
		"familyName": "Rao",
	}
	assert a["titles"][1]["titleType"] == "TranslatedTitle"
	assert {"alternateIdentifier": "ark:/12345/r7b2", "alternateIdentifierType": "ARK"} in a[
		"alternateIdentifiers"
	]
	assert a["relatedIdentifiers"][0]["relatedIdentifier"] == "https://archive.org/details/kanakadasa1950"
	assert a["contributors"][0]["name"] == "Kannada Sahitya Parishat"
	bare = dc.attributes({"item_id": "x"}, "u", "", 2026)
	assert (
		bare["creators"] == [{"name": ":unav", "nameType": "Organizational"}]
		and bare["publicationYear"] == 2026
	)


def test_fingerprint_and_payload():
	a = dc.attributes(RECORD, "u", "P", 2026)
	assert dc.fingerprint(a) == dc.fingerprint(dict(a))
	assert dc.fingerprint(a) != dc.fingerprint({**a, "url": "v"})
	body = dc.payload("10.1/X", a)
	assert body["data"]["attributes"]["event"] == "publish" and body["data"]["attributes"]["doi"] == "10.1/X"
	assert "event" not in dc.payload("10.1/X", a, None)["data"]["attributes"]
	assert dc.error_text({"errors": [{"source": "url", "title": "Can't be blank"}]}) == "url: Can't be blank"


def test_a_doi_is_cited():
	from sok_resdesk.core import citations as c

	item = {**RECORD, "doi": "10.12345/RD.KANAKADASA1950"}
	assert c.to_apa(item, "https://lib.example").endswith("https://doi.org/10.12345/RD.KANAKADASA1950")
	assert "doi = {10.12345/RD.KANAKADASA1950}" in c.to_bibtex(item, "https://lib.example")
	assert "DO  - 10.12345/RD.KANAKADASA1950" in c.to_ris(item, "https://lib.example")
	assert c.to_csl(item)["DOI"] == "10.12345/RD.KANAKADASA1950"
	assert ("citation_doi", "10.12345/RD.KANAKADASA1950") in c.highwire_tags(item, "https://lib.example")
	page = c.with_page(item, 5, "3", "https://lib.example")
	assert "/n5" in c.to_apa(page, "https://lib.example")  # a page citation links to its page
