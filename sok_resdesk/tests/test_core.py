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


def test_page_citations():
	base = "https://lib.example"
	item = citations.with_page(sample_item(), 41, "42", base)
	assert item["page_url"] == f"{base}/library/item/{item['item_id']}?page=41&view=text"
	assert citations.page_phrase(item) == "p. 42"
	assert "pages = {42}" in citations.to_bibtex(item, base)
	assert "SP  - 42" in citations.to_ris(item, base)
	assert citations.to_csl(item, base)["page"] == "42"
	assert "p. 42." in citations.to_apa(item, base) and item["page_url"] in citations.to_apa(item, base)
	assert ", p. 42." in citations.to_mla(item, base)
	assert ", 42." in citations.to_chicago(item, base)
	# a page with no printed number is named by its leaf; with an ARK the link is the page's ARK
	bare = citations.with_page({**sample_item(), "persistent_id": "ark:/12345/b1x"}, 7, "", base)
	assert citations.page_phrase(bare) == "leaf 7"
	assert bare["page_url"] == f"{base}/ark:/12345/b1x/n7"
	assert "pages = {leaf 7}" in citations.to_bibtex(bare, base)
	# roman front matter keeps its label
	assert citations.page_phrase(citations.with_page(sample_item(), 3, "xii", base)) == "xii"
	# the book's own citation is unchanged
	assert "pages" not in citations.to_bibtex(sample_item(), base)
	assert "page" not in citations.to_csl(sample_item(), base)


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
		rows = [
			i
			for i in self.items
			if (not from_ or i["modified"] >= from_) and (not until or i["modified"] <= until)
		]
		return rows[start : start + limit], len(rows)


def repo():
	return oai.Repository(
		FakeStore(), "resdesk.example.org", "Test", "https://resdesk.example.org", "a@b.org"
	)


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
	doc = parse(
		r.handle(
			{
				"verb": "GetRecord",
				"identifier": "oai:resdesk.example.org:item0001",
				"metadataPrefix": "oai_dc",
			}
		)
	)
	assert doc.getElementsByTagName("dc:title")
	doc = parse(
		r.handle(
			{
				"verb": "GetRecord",
				"identifier": "oai:resdesk.example.org:item0001",
				"metadataPrefix": "marc21",
			}
		)
	)
	assert doc.getElementsByTagName("datafield")
	doc = parse(
		r.handle(
			{"verb": "GetRecord", "identifier": "oai:resdesk.example.org:nope", "metadataPrefix": "oai_dc"}
		)
	)
	assert doc.getElementsByTagName("error")[0].getAttribute("code") == "idDoesNotExist"


# -- access control -------------------------------------------------------------------


def test_access_matrix():
	from sok_resdesk.core import access as a

	P, R, F = a.PUBLIC, a.LOGIN_TO_READ, a.LOGIN_TO_FIND
	# members see and read everything, whatever the guest mode
	for mode in a.GUEST_MODES:
		for vis in a.VISIBILITIES:
			assert a.can_find(vis, mode, True) and a.can_read(vis, mode, True)
	# guests, item mode
	assert a.can_find(P, a.GUEST_ITEM, False) and a.can_read(P, a.GUEST_ITEM, False)
	assert a.can_find(R, a.GUEST_ITEM, False) and not a.can_read(R, a.GUEST_ITEM, False)
	assert not a.can_find(F, a.GUEST_ITEM, False) and not a.can_read(F, a.GUEST_ITEM, False)
	# records only: find public + login-to-read, read nothing
	assert a.can_find(P, a.GUEST_RECORDS, False) and not a.can_read(P, a.GUEST_RECORDS, False)
	assert not a.can_find(F, a.GUEST_RECORDS, False)
	# login required: nothing
	assert not a.can_find(P, a.GUEST_NONE, False)
	# empty / unknown visibility counts as Public
	assert a.can_read(None, a.GUEST_ITEM, False) and a.can_read("", None, False)


def test_access_search_filters():
	from sok_resdesk.core import access as a

	assert a.search_filter("books", a.GUEST_ITEM, True) is None
	assert a.search_filter("books", a.GUEST_ITEM, False) == 'NOT visibility = "Login to find"'
	assert (
		a.search_filter("pages", a.GUEST_ITEM, False)
		== 'NOT visibility IN ["Login to read", "Login to find"]'
	)
	assert a.search_filter("pages", a.GUEST_RECORDS, False) == ""
	assert a.search_filter("books", a.GUEST_RECORDS, False) == 'NOT visibility = "Login to find"'
	assert a.search_filter("books", a.GUEST_NONE, False) == ""
	assert a.sql_condition(a.GUEST_NONE, False) == "1=0"
	assert a.sql_condition(a.GUEST_ITEM, True) == "1=1"


def test_access_initial_visibility():
	from sok_resdesk.core import access as a

	record = sample_item()
	rules = [
		{"match_on": "Subject", "value": "nothing here", "visibility": a.LOGIN_TO_FIND},
		{"match_on": "Collection", "value": "jaigyan", "visibility": a.LOGIN_TO_READ},
		{"match_on": "Language", "value": "Kannada", "visibility": a.LOGIN_TO_FIND},
	]
	# first matching rule wins, case-insensitively
	assert a.initial_visibility(record, None, rules, a.PUBLIC) == (
		a.LOGIN_TO_READ,
		"Rule: Collection = jaigyan",
	)
	# the profile's own setting beats rules
	assert a.initial_visibility(record, a.PUBLIC, rules, a.LOGIN_TO_FIND) == (a.PUBLIC, "Profile")
	# no rule matches: site default; a bad default falls back to Public
	assert a.initial_visibility(record, "", [], a.LOGIN_TO_READ) == (a.LOGIN_TO_READ, "Default")
	assert a.initial_visibility(record, "", [], "nonsense") == (a.PUBLIC, "Default")
	lang = [{"match_on": "Language", "value": "kan", "visibility": a.LOGIN_TO_FIND}]
	assert a.initial_visibility(record, None, lang, a.PUBLIC)[0] == a.LOGIN_TO_FIND
	prof = [{"match_on": "Ingest Profile", "value": "Staff scans", "visibility": a.LOGIN_TO_FIND}]
	assert (
		a.initial_visibility({**record, "ingest_profile": "Staff scans"}, None, prof, a.PUBLIC)[0]
		== a.LOGIN_TO_FIND
	)


def test_collections_core():
	from sok_resdesk.core import collections as c

	assert c.slugify("Kannada Literature: Vachanas & more") == "kannada-literature-vachanas-more"
	assert c.slugify("ಕನ್ನಡ ಸಾಹಿತ್ಯ") == "ಕನ್ನಡ-ಸಾಹಿತ್ಯ"
	assert c.slugify("  !! ") == "collection"
	rec = {
		"subjects": ["Archaeology -- Karnataka"],
		"collections": ["JaiGyan"],
		"item_type": "Periodical",
		"language_label": "Kannada",
		"language": "kan",
	}
	assert c.matches(rec, [{"match_on": "Subject", "how": "contains", "value": "archaeology"}])
	assert not c.matches(rec, [{"match_on": "Subject", "value": "archaeology"}])
	assert c.matches(rec, [{"match_on": "Source Collection", "value": "jaigyan"}])
	assert c.matches(rec, [{"match_on": "Document Type", "value": "Periodical"}])
	assert c.matches(rec, [{"match_on": "Language", "value": "kan"}])
	assert not c.matches(rec, [])


def test_item_types_and_citations():
	from sok_resdesk.core.citations import to_bibtex, to_csl, to_ris

	assert (
		normalize.guess_item_type({"title": "Kannada Sahitya Patrike", "subject": "Periodicals"})
		== "Periodical"
	)
	assert normalize.guess_item_type({"title": "A study", "subject": "Thesis (Ph.D.)"}) == "Thesis"
	assert normalize.guess_item_type({"title": "Ivaru Kanda Vijayanagara"}) == "Book"
	item = {**sample_item(), "item_type": "Thesis"}
	assert to_bibtex(item).startswith("@phdthesis{")
	assert to_ris(item).startswith("TY  - THES")
	assert to_csl(item)["type"] == "thesis"


def _rec():
	r = sample_item()
	r.update(
		{
			"item_type": "Book",
			"curated_collections": ["kannada-lit"],
			"visibility": "Public",
			"published": True,
		}
	)
	return r


def test_spreadsheet_round_trip():
	from sok_resdesk.core import metaio

	rec = _rec()
	row = metaio.record_to_row(rec, "https://lib.example.org")
	assert (
		row["creators"] == "ಶ್ರೀ ಕೆ ಸುಭಾಶ್ಚಂದ್ರ ಶೆಣೈ"
		and row["year"] == "1955"
		and row["collections"] == "kannada-lit"
	)
	csv_text = metaio.rows_to_csv([row])
	back = metaio.csv_to_rows(csv_text.encode("utf-8"))[0]
	assert back == row
	# nothing edited -> no changes
	assert metaio.row_changes(back, rec) == ({}, [])
	# edit a few cells, drop most columns
	edited = {
		"item_id": rec["item_id"],
		"title": "New title",
		"subjects": "A; B",
		"year": "1956",
		"item_type": "periodical",
		"visibility": "login to read",
		"published": "0",
	}
	changes, problems = metaio.row_changes(edited, rec)
	assert problems == []
	assert changes == {
		"title": "New title",
		"subjects": ["A", "B"],
		"year": 1956,
		"item_type": "Periodical",
		"visibility": "Login to read",
		"published": False,
	}
	_, problems = metaio.row_changes({"item_id": "x", "year": "c. 1950", "item_type": "Poster"}, rec)
	assert len(problems) == 2


def test_export_formats():
	import csv as _csv
	import io as _io
	import xml.dom.minidom as md

	from sok_resdesk.core import metaio

	rec = _rec()
	md.parseString(metaio.dublin_core_collection([rec], "https://x.org"))
	mods = metaio.mods_collection([rec], "https://x.org")
	md.parseString(mods)
	assert '<genre authority="local">book</genre>' in mods
	graph = json.loads(metaio.jsonld_graph([rec], "https://x.org"))
	assert graph["@graph"][0]["@type"] and "@context" not in graph["@graph"][0]
	meta = metaio.meta_xml(rec)
	md.parseString(meta)
	assert "<subject>ಒಂದಾಣೆ ಮಾಲೆ</subject>" in meta
	rows = list(_csv.DictReader(_io.StringIO(metaio.ia_bulk_csv([rec], "ServantsOfKnowledge"))))
	assert rows[0]["identifier"] == rec["item_id"] and rows[0]["subject[1]"] == "ಕನ್ನಡ ಸಾಹಿತ್ಯ"
	assert rows[0]["collection"] == "ServantsOfKnowledge" and rows[0]["mediatype"] == "texts"
	j = metaio.json_record(rec, "https://x.org")
	assert j["portal_url"].startswith("https://x.org/library/item/") and j["citation_type"] == "book"


def test_quiet_hours():
	import datetime as dt

	from sok_resdesk.core.quiet import in_quiet_hours, minutes

	wed = dt.datetime(2026, 9, 30, 10, 0)  # a Wednesday
	assert in_quiet_hours(wed, "09:00", "18:00")
	assert not in_quiet_hours(wed.replace(hour=18), "09:00", "18:00")
	assert not in_quiet_hours(wed.replace(hour=8, minute=59), "09:00:00", dt.timedelta(hours=18))
	# overnight
	assert in_quiet_hours(wed.replace(hour=23), "22:00", "06:00")
	assert in_quiet_hours(wed.replace(hour=5), "22:00", "06:00")
	assert not in_quiet_hours(wed.replace(hour=12), "22:00", "06:00")
	# weekdays only: Saturday daytime runs freely; Friday night into Saturday counts as Friday
	sat = dt.datetime(2026, 10, 3, 10, 0)
	assert not in_quiet_hours(sat, "09:00", "18:00", weekdays_only=True)
	assert in_quiet_hours(sat.replace(hour=2), "22:00", "06:00", weekdays_only=True)
	assert not in_quiet_hours(dt.datetime(2026, 10, 4, 2, 0), "22:00", "06:00", weekdays_only=True)
	# unset or equal = never
	assert not in_quiet_hours(wed, None, "18:00") and not in_quiet_hours(wed, "09:00", "09:00")
	assert minutes(dt.time(7, 45)) == 465


def test_book_capacity():
	from sok_resdesk.core import capacity as cap

	GB = cap.GB
	# a laptop-sized Docker: 2 CPUs, 8 GB, 250 GB free on a 300 GB disk, empty catalogue
	e = cap.estimate(2, 8 * GB, 300 * GB, 250 * GB)
	assert e["known"] and e["by"] == "memory" and e["pages_per_book"] == 184
	assert 15_000 < e["capacity_books"] < 20_000
	assert e["books"]["cpu"] > e["books"]["memory"] and e["books"]["disk"] > e["books"]["memory"]
	# the recommended minimum server for 50,000 books holds about that many
	e = cap.estimate(4, 16 * GB, 300 * GB, 290 * GB)
	assert 40_000 < e["capacity_books"] < 60_000
	# a nearly full disk is the limit, and what is already stored counts as usable
	e = cap.estimate(8, 32 * GB, 100 * GB, 12 * GB, books=1000, pages=184_000)
	assert e["by"] == "disk"
	assert e["books"]["disk"] > 1000  # the books already here fit, of course
	# the library's own average page count once there are enough books
	assert cap.pages_per_book(10, 5000) == cap.DEFAULT_PAGES_PER_BOOK
	assert cap.pages_per_book(100, 40_000) == 400
	# limits: automatic, a chosen number of books, none
	machine = cap.estimate(2, 8 * GB, 300 * GB, 250 * GB)
	assert cap.limit_units("auto", 0, machine, 0, 0) == machine["capacity_units"]
	assert cap.limit_units("none", 0, machine, 0, 0) is None
	units = cap.limit_units("custom", 10, machine, 0, 0)
	assert round(units) == round(10 * (184 + cap.BOOK_UNITS))
	assert cap.limit_units("custom", 0, machine, 0, 0) == machine["capacity_units"]  # 0 = not chosen
	assert cap.limit_units("auto", 0, {"known": False}, 0, 0) is None
	# room: pages count, a book without text still takes a little
	assert cap.room(units, 9, 9 * 184) and not cap.room(units, 10, 10 * 184)
	assert not cap.room(units, 9, 9 * 184, new_pages=400)  # a thick book doesn't fit
	assert cap.room(None, 10**9, 10**12)
	assert cap.estimate(0, None, None, None)["known"] is False


def test_versions_and_release_notes():
	from sok_resdesk.core import updates as upd

	assert upd.parse_version("v0.10.1") == (0, 10, 1) == upd.parse_version("0.10.1")
	assert upd.parse_version("main") is None and upd.parse_version("v1.0.0-rc1") is None
	assert upd.is_newer("v0.11.0", "0.10.1") and not upd.is_newer("v0.9.9", "0.10.0")
	assert not upd.is_newer(None, "0.10.0") and not upd.is_newer("v0.11.0", "")
	tags = ["v0.9.0", "v0.10.0", "v0.10.1", "v0.2.0", "nightly", "v16.1.0"]
	assert upd.latest_release(tags) == "v16.1.0" and upd.latest_release(tags, major=0) == "v0.10.1"
	assert upd.latest_release([]) is None
	assert upd.releases_between(tags, "0.9.0", "v0.10.1") == ["v0.10.1", "v0.10.0"]
	changelog = """# Changelog

## 0.11.0 (2026-10-02): the Server page

- Upgrades from the Desk
- NEEDS-REINDEX

## 0.10.1 (2026-09-30): gentler workers

- nice 19

## 0.10.0 (2026-09-30): resources
- presets
"""
	notes = upd.changelog_sections(changelog, "0.10.0")
	assert [n["version"] for n in notes] == ["0.11.0", "0.10.1"]
	assert notes[0]["date"] == "2026-10-02" and notes[0]["title"] == "the Server page"
	assert "Upgrades from the Desk" in notes[0]["notes"] and upd.needs_reindex(notes)
	assert [n["version"] for n in upd.changelog_sections(changelog, "0.10.0", "v0.10.1")] == ["0.10.1"]
	assert not upd.needs_reindex(upd.changelog_sections(changelog, "0.10.0", "0.10.1"))
	assert upd.safe_release_ref("latest") == "latest" and upd.safe_release_ref("0.11.0") == "v0.11.0"
	assert upd.safe_release_ref("v0.11.0") == "v0.11.0" and upd.safe_release_ref("main") == "main"
	for bad in ("v0.11.0; rm -rf /", "--help", "HEAD~1", "../x"):
		try:
			upd.safe_release_ref(bad)
			raise AssertionError(bad)
		except ValueError:
			pass


def test_updater_helper_commands():
	"""The helper only runs a short list of commands, with checked arguments."""
	import importlib.util
	from pathlib import Path

	spec = importlib.util.spec_from_file_location(
		"agent", Path(__file__).resolve().parents[2] / "scripts" / "agent.py"
	)
	agent = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(agent)
	docker, native = {"INSTALL_MODE": "docker"}, {"INSTALL_MODE": "native"}
	assert agent.command_for("upgrade", {}, docker) == ["./upgrade.sh", "--yes"]
	assert agent.command_for("upgrade", {"target": "v0.11.0", "backup": 0, "frappe": 0}, docker) == [
		"./upgrade.sh",
		"--yes",
		"v0.11.0",
		"--no-backup",
		"--no-frappe",
	]
	assert agent.command_for("upgrade", {"target": "main"}, docker) == ["./upgrade.sh", "--yes", "--main"]
	assert agent.command_for("upgrade", {"target": "v1; reboot"}, docker) is None
	assert agent.command_for("restart", {"service": "workers"}, docker) == [
		"docker",
		"compose",
		"restart",
		"queue",
	]
	assert agent.command_for("restart", {"service": "db"}, docker) is None
	assert agent.command_for("restart", {"service": "workers"}, native) is None
	assert agent.command_for("restart", {"service": "all"}, native) == ["./resdesk.sh", "restart"]
	assert agent.command_for("apply_resources", {"preset": "light"}, docker) == [
		"./resdesk.sh",
		"resources",
		"light",
	]
	assert agent.command_for("apply_resources", {"preset": "huge"}, docker) is None
	# a number of parallel workers chosen in Settings, on Docker and native installs alike
	assert agent.command_for("apply_resources", {"workers": 6}, docker) == [
		"./resdesk.sh",
		"resources",
		"set",
		"QUEUE_WORKERS=6",
	]
	assert agent.command_for("apply_resources", {"workers": 6}, native)[-1] == "QUEUE_WORKERS=6"
	for bad in (0, 17, "4; rm -rf /", -1):
		assert agent.command_for("apply_resources", {"workers": bad}, docker) is None
	assert agent.command_for("server_backup", {}, native) == ["./resdesk.sh", "backup"]
	# installing tools: native installs only, and only the two known parts
	assert agent.command_for("install_requirements", {"part": "ocr"}, native) == [
		"./resdesk.sh",
		"requirements",
		"install",
		"ocr",
	]
	assert agent.command_for("install_requirements", {"part": "ocr"}, docker) is None
	assert agent.command_for("install_requirements", {"part": "curl evil | sh"}, native) is None
	assert agent.command_for("rm", {}, docker) is None


def test_migrate_fingerprint(tmp_path):
	from sok_resdesk.core import schema

	bench = tmp_path
	(bench / "sites" / "site1").mkdir(parents=True)
	(bench / "sites" / "apps.txt").write_text("frappe\nsok_resdesk\n")
	files = {
		"frappe/frappe/__init__.py": '__version__ = "16.1.0"',
		"frappe/frappe/core/doctype/user/user.json": "{}",
		"frappe/frappe/core/doctype/user/user.py": "x = 1",
		"frappe/frappe/public/build.json": "{}",
		"sok_resdesk/sok_resdesk/__init__.py": '__version__ = "1.0.0"',
		"sok_resdesk/sok_resdesk/hooks.py": "app_name = 'sok_resdesk'",
		"sok_resdesk/sok_resdesk/patches.txt": "[post_model_sync]",
		"sok_resdesk/sok_resdesk/patches/v1/p.py": "def execute(): pass",
		"sok_resdesk/sok_resdesk/setup.py": "def after_migrate(): pass",
		"sok_resdesk/sok_resdesk/search.py": "x = 1",
		"sok_resdesk/sok_resdesk/resdesk/doctype/rd_item/rd_item.json": "{}",
	}
	for rel, text in files.items():
		p = bench / "apps" / rel
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(text)
	assert "core/doctype/user/user.json" in schema.app_files(str(bench), "frappe")
	assert "public/build.json" not in schema.app_files(str(bench), "frappe")
	assert "patches/v1/p.py" in schema.app_files(str(bench), "sok_resdesk")

	first = schema.fingerprint(str(bench))
	assert first == schema.fingerprint(str(bench))

	def changed(rel, text="changed"):
		p = bench / "apps" / rel
		old = p.read_text()
		p.write_text(text)
		result = schema.fingerprint(str(bench)) != first
		p.write_text(old)
		return result

	# what migrate acts on
	for rel in (
		"frappe/frappe/__init__.py",
		"frappe/frappe/core/doctype/user/user.json",
		"sok_resdesk/sok_resdesk/hooks.py",
		"sok_resdesk/sok_resdesk/patches.txt",
		"sok_resdesk/sok_resdesk/patches/v1/p.py",
		"sok_resdesk/sok_resdesk/setup.py",
		"sok_resdesk/sok_resdesk/resdesk/doctype/rd_item/rd_item.json",
	):
		assert changed(rel), rel
	# ordinary code changes don't need a migrate
	for rel in (
		"frappe/frappe/core/doctype/user/user.py",
		"frappe/frappe/public/build.json",
		"sok_resdesk/sok_resdesk/search.py",
	):
		assert not changed(rel), rel
	assert schema.fingerprint(str(bench)) == first

	# no database settings: can't tell, so migrate
	assert schema.stored(str(bench), "site1") is None
	assert schema.needs_migrate(str(bench), "site1")[0]
	assert schema.needs_migrate(str(bench), "nosite") == (True, "no such site")
	schema.stored = lambda b, s: first
	try:
		assert schema.needs_migrate(str(bench), "site1") == (
			False,
			"the database is up to date with the code",
		)
	finally:
		import importlib

		importlib.reload(schema)
