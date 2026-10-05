"""0.61: OPDS feeds for e-reader apps."""

from xml.etree import ElementTree as ET

from sok_resdesk.core import opds

NS = {"a": "http://www.w3.org/2005/Atom"}
BASE = "https://lib.example.org"
BOOK = {
	"item_id": "ph&1",
	"title": "A <title> & more",
	"authors": ["Anne Author"],
	"language": "kan",
	"summary": "About it",
	"updated": "2026-01-02T03:04:05Z",
	"cover": BASE + "/c.jpg",
	"files": [(BASE + "/f?name=b.epub", "b.epub"), (BASE + "/f?name=b.pdf", "b.pdf")],
}


def test_a_book_entry_is_well_formed_with_a_link_per_file():
	xml = opds.feed(
		BASE,
		title="Lib",
		path="/opds/new",
		kind="acq",
		updated="2026-01-01T00:00:00Z",
		entries=[opds.entry(BASE, BOOK)],
	)
	root = ET.fromstring(xml)
	e = root.find("a:entry", NS)
	assert e.find("a:title", NS).text == "A <title> & more"
	acq = [
		(link.get("type"), link.get("href"))
		for link in e.findall("a:link", NS)
		if link.get("rel") == "http://opds-spec.org/acquisition/open-access"
	]
	assert acq == [
		("application/epub+zip", BASE + "/f?name=b.epub"),
		("application/pdf", BASE + "/f?name=b.pdf"),
	]
	assert e.find("a:author/a:name", NS).text == "Anne Author"


def test_a_book_without_files_has_no_download_only_its_page():
	xml = opds.feed(
		BASE,
		title="L",
		path="/opds",
		kind="acq",
		updated="u",
		entries=[opds.entry(BASE, {**BOOK, "files": []})],
	)
	rels = [link.get("rel") for link in ET.fromstring(xml).find("a:entry", NS).findall("a:link", NS)]
	assert "http://opds-spec.org/acquisition/open-access" not in rels and "alternate" in rels


def test_a_feed_links_to_itself_the_start_search_and_the_next_page():
	xml = opds.feed(
		BASE, title="L", path="/opds/new", kind="acq", updated="u", entries=[], nxt="/opds/new?page=2"
	)
	links = {link.get("rel"): link.get("href") for link in ET.fromstring(xml).findall("a:link", NS)}
	assert links["self"] == BASE + "/opds/new" and links["start"] == BASE + "/opds"
	assert links["next"] == BASE + "/opds/new?page=2" and links["search"].endswith("/opds/opensearch.xml")
	assert "{searchTerms}" in opds.opensearch(BASE, "Lib")


def test_mime_types_of_book_files():
	assert opds.mime_of("a.EPUB") == "application/epub+zip"
	assert opds.mime_of("noext") == "application/octet-stream"
