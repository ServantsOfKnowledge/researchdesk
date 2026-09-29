"""Unit tests for the Frappe-independent core. Run with: pytest sok_resdesk/tests/test_core.py"""

import json
import xml.dom.minidom
from datetime import datetime

from sok_resdesk.core import citations, marc, normalize, oai
from sok_resdesk.core.ia import IAClient

SAMPLE_META = {
	"identifier": "1857rasipayidhan0000srik",
	"title": '೧೮೫೭ರ "ಸಿಪಾಯಿ ದಂಗೆ" ೪೬',
	"alt_title": '1857 Ra "Sipayi Dhangye" 46',
	"creator": "ಶ್ರೀ ಕೆ ಸುಭಾಶ್ಚಂದ್ರ ಶೆಣೈ",
	"alt_creator": "Sri K.Subashchandra Shenoy",
	"date": "1955",
	"language": "kan",
	"publisher": "ಒಂದಾಣೆ ಮಾಲೆ, ಮಂಗಳೂರು",
	"subject": "ಒಂದಾಣೆ ಮಾಲೆ;ಕನ್ನಡ ಸಾಹಿತ್ಯ",
	"collection": ["ServantsOfKnowledge", "JaiGyan", "fav-someone"],
	"imagecount": "22",
	"licenseurl": "http://creativecommons.org/licenses/by-nc-sa/4.0/",
	"identifier-ark": "ark:/13960/t0qs4zh21",
	"description": "<p>A <b>small</b> book</p>",
}
SAMPLE_FILES = [{"name": "1857rasipayidhan0000srik_hocr_searchtext.txt.gz"}]


def sample_item():
	return normalize.normalize_ia_item("1857rasipayidhan0000srik", SAMPLE_META, SAMPLE_FILES)


# -- normalisation ---------------------------------------------------------------

def test_language_variants():
	for raw in ("Kan", "kan", "Kannada", "KAN", "kn"):
		assert normalize.normalize_language(raw) == ("kan", "Kannada")
	assert normalize.normalize_language("ori") == ("ory", "Odia")
	assert normalize.normalize_language(["eng", "kan"]) == ("mul", "English; Kannada")
	assert normalize.normalize_language(None) == ("", "")
	assert normalize.normalize_language("xyz")[0] == "xyz"


def test_year_and_decade():
	assert normalize.parse_year("1946-01-01T00:00:00Z") == 1946
	assert normalize.parse_year("c. 1890?") == 1890
	assert normalize.parse_year("undated") is None
	assert normalize.decade_of(1955) == "1950s"


def test_normalize_item():
	item = sample_item()
	assert item["year"] == 1955
	assert item["language"] == "kan"
	assert item["subjects"] == ["ಒಂದಾಣೆ ಮಾಲೆ", "ಕನ್ನಡ ಸಾಹಿತ್ಯ"]
	assert item["collections"] == ["ServantsOfKnowledge", "JaiGyan"]
	assert item["description"] == "A small book"
	assert item["page_count"] == 22
	assert item["has_page_text"] is True
	assert item["access_status"] == "Open"


def test_restricted_items_have_no_fulltext():
	meta = dict(SAMPLE_META, **{"access-restricted-item": "true"})
	item = normalize.normalize_ia_item("x", meta, SAMPLE_FILES)
	assert item["access_status"] == "Restricted"
	assert item["has_fulltext"] is False


# -- IA query building --------------------------------------------------------

def test_build_query():
	q = IAClient.build_query("Collection", "ServantsOfKnowledge", "language:kan")
	assert q == "collection:(ServantsOfKnowledge) AND (language:kan) AND mediatype:(texts)"
	q = IAClient.build_query("Identifier List", identifiers=["a", " b ", ""])
	assert q == "identifier:(a OR b)"
	q = IAClient.build_query("Search Query", query="title:vachana")
	assert q.startswith("(title:vachana)")


# -- citations ----------------------------------------------------------------

def test_bibtex():
	bib = citations.render(sample_item(), "bibtex")
	assert bib.startswith("@book{shenoy1955sipayi,")
	assert "[Sri K.Subashchandra Shenoy]" in bib
	assert "year = {1955}" in bib
	assert "Kannada" in bib


def test_ris_and_csl():
	ris = citations.render(sample_item(), "ris")
	assert ris.startswith("TY  - BOOK") and ris.rstrip().endswith("ER  -")
	assert "A2  - Sri K.Subashchandra Shenoy" in ris
	csl = json.loads(citations.render(sample_item(), "csl-json"))
	assert csl[0]["type"] == "book" and csl[0]["issued"] == {"date-parts": [[1955]]}


def test_styles():
	item = sample_item()
	apa = citations.to_apa(item)
	assert apa.startswith("Shenoy, K. S. (1955).")
	mla = citations.to_mla(item)
	assert mla.startswith("Shenoy, K.Subashchandra.")
	chicago = citations.to_chicago(item)
	assert "1955" in chicago and "archive.org" in chicago


def test_split_name():
	assert citations.split_name("Rangachari, K.") == ("Rangachari", "K.")
	assert citations.split_name("K. Rangachari") == ("Rangachari", "K.")
	assert citations.split_name("Kuvempu") == ("Kuvempu", "")
	assert citations.split_name("Dr. S. L. Bhyrappa") == ("Bhyrappa", "S. L.")


def test_json_ld_and_highwire():
	item = sample_item()
	ld = citations.json_ld(item, "https://library.example.org")
	assert ld["@type"] == "Book" and ld["url"].endswith("/library/item/1857rasipayidhan0000srik")
	tags = dict(citations.highwire_tags(item))
	assert tags["citation_publication_date"] == "1955"


# -- MARC ----------------------------------------------------------------------

def test_marcxml_is_valid_xml():
	xml_text = marc.to_marcxml_collection([sample_item()], "https://library.example.org")
	doc = xml.dom.minidom.parseString(xml_text.encode())
	fields = {f.getAttribute("tag") for f in doc.getElementsByTagName("datafield")}
	assert {"100", "245", "246", "264", "856"} <= fields
	control = {f.getAttribute("tag"): f.firstChild.data for f in doc.getElementsByTagName("controlfield")}
	assert len(control["008"]) == 40
	assert control["008"][35:38] == "kan"


# -- OAI-PMH ------------------------------------------------------------------

class FakeStore:
	def __init__(self, n=250):
		self.items = []
		for i in range(n):
			item = sample_item()
			item["item_id"] = f"item{i:04d}"
			item["modified"] = datetime(2026, 1, 1 + i % 28)
			item["set_specs"] = ["ServantsOfKnowledge"]
			self.items.append(item)

	def earliest(self):
		return datetime(2026, 1, 1)

	def sets(self):
		return [("ServantsOfKnowledge", "Servants of Knowledge")]

	def get(self, item_id):
		return next((i for i in self.items if i["item_id"] == item_id), None)

	def list(self, start, limit, from_, until, set_spec):
		rows = [i for i in self.items if (not from_ or i["modified"] >= from_) and (not until or i["modified"] <= until)]
		return rows[start:start + limit], len(rows)


def repo():
	return oai.Repository(FakeStore(), "resdesk.example.org", "Test", "https://resdesk.example.org", "a@b.org")


def parse(xml_text):
	return xml.dom.minidom.parseString(xml_text.encode())


def test_oai_identify_and_errors():
	doc = parse(repo().handle({"verb": "Identify"}))
	assert doc.getElementsByTagName("repositoryName")[0].firstChild.data == "Test"
	doc = parse(repo().handle({"verb": "Nope"}))
	assert doc.getElementsByTagName("error")[0].getAttribute("code") == "badVerb"
	doc = parse(repo().handle({"verb": "ListRecords"}))
	assert doc.getElementsByTagName("error")[0].getAttribute("code") == "badArgument"


def test_oai_paging_with_resumption_token():
	r = repo()
	doc = parse(r.handle({"verb": "ListIdentifiers", "metadataPrefix": "oai_dc"}))
	assert len(doc.getElementsByTagName("header")) == 100
	token = doc.getElementsByTagName("resumptionToken")[0]
	assert token.getAttribute("completeListSize") == "250"
	seen = 100
	while token.firstChild:
		doc = parse(r.handle({"verb": "ListIdentifiers", "resumptionToken": token.firstChild.data}))
		seen += len(doc.getElementsByTagName("header"))
		token = doc.getElementsByTagName("resumptionToken")[0]
	assert seen == 250


def test_oai_get_record_formats():
	r = repo()
	doc = parse(r.handle({"verb": "GetRecord", "identifier": "oai:resdesk.example.org:item0001", "metadataPrefix": "oai_dc"}))
	assert doc.getElementsByTagName("dc:title")
	doc = parse(r.handle({"verb": "GetRecord", "identifier": "oai:resdesk.example.org:item0001", "metadataPrefix": "marc21"}))
	assert doc.getElementsByTagName("datafield")
	doc = parse(r.handle({"verb": "GetRecord", "identifier": "oai:resdesk.example.org:nope", "metadataPrefix": "oai_dc"}))
	assert doc.getElementsByTagName("error")[0].getAttribute("code") == "idDoesNotExist"
