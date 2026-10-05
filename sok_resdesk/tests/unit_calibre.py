"""0.51: a Calibre library read as a store of books (no Frappe)."""

import hashlib
import os
import sqlite3

import pytest

from sok_resdesk.core import calibre
from sok_resdesk.core.folder import StoreError
from sok_resdesk.tests import calibre_fixtures as fx


@pytest.fixture
def lib(tmp_path):
	return fx.make_library(str(tmp_path / "Calibre Library"))


def test_a_library_is_known_by_its_metadata_db(lib, tmp_path):
	assert calibre.is_library(lib)
	assert not calibre.is_library(str(tmp_path))
	with pytest.raises(StoreError):
		calibre.CalibreStore(str(tmp_path))


def test_every_book_has_a_stable_identifier_from_its_uuid(lib):
	items = dict(calibre.CalibreStore(lib).iter_items())
	assert items == {
		fx.ID_EPUB: "Kanakadasa/Kirtanegalu (1)",
		fx.ID_PDF: "Smith, John/Typed notes (2)",
		fx.ID_BARE: "Kanakadasa/File went missing (3)",
	}
	assert len(list(calibre.CalibreStore(lib).iter_items(limit=2))) == 2


def test_the_details_come_across(lib):
	store = calibre.CalibreStore(lib)
	data = store.load_item(fx.ID_EPUB, "Kanakadasa/Kirtanegalu (1)")
	m = data["metadata"]
	assert m["title"] == "Kirtanegalu"
	assert m["creator"] == ["Kanakadasa", "Smith, John"]  # Calibre keeps a comma in a name as "|"
	assert (m["date"], m["publisher"], m["language"]) == ("1931-05-01", "Mysore Press", ["kan", "eng"])
	assert sorted(m["subject"]) == ["devotional", "poetry"]
	assert m["series"] == "Dasa Sahitya #2" and m["isbn"] == "9780000000002"
	assert "Kanakadasa" in m["description"]
	assert m["calibre"]["custom"] == {"Shelf": "Rack 7", "Read Pages": "120"}
	assert m["calibre"]["identifiers"]["goodreads"] == "77" and m["calibre"]["rating"] == 8
	assert [f["name"] for f in data["files"]] == [
		"Kirtanegalu - Kanakadasa.epub",
		"Kirtanegalu - Kanakadasa.mobi",
		"cover.jpg",
		"metadata.opf",
	]


def test_calibres_no_date_is_not_a_year(lib):
	m = calibre.CalibreStore(lib).load_item(fx.ID_PDF, "Smith, John/Typed notes (2)")["metadata"]
	assert "date" not in m


def test_files_the_library_lost_are_not_offered(lib):
	store = calibre.CalibreStore(lib)
	loc = "Kanakadasa/File went missing (3)"
	assert store.downloads(loc) == [] and store.pdf_name(fx.ID_BARE, loc) is None


def test_pdf_cover_and_downloads(lib):
	store = calibre.CalibreStore(lib)
	loc = "Kanakadasa/Kirtanegalu (1)"
	assert store.pdf_name(fx.ID_EPUB, loc) is None  # an e-book: catalogued and downloadable, text later
	assert store.thumb_name(loc) == "cover.jpg"
	assert store.downloads(loc) == ["Kirtanegalu - Kanakadasa.epub", "Kirtanegalu - Kanakadasa.mobi"]
	assert store.pdf_name(fx.ID_PDF, "Smith, John/Typed notes (2)") == "Typed notes - John Smith.pdf"
	assert store.read(loc, "Kirtanegalu - Kanakadasa.epub") == fx.EPUB


def test_files_outside_the_library_are_never_read(lib):
	store = calibre.CalibreStore(lib)
	with pytest.raises(StoreError):
		store.file_path("Kanakadasa/Kirtanegalu (1)", "../../../../etc/passwd")
	with pytest.raises(StoreError):
		store.file_path("no/such/book", "x")


def test_the_signature_changes_when_the_book_does_and_the_library_is_never_written(lib):
	store = calibre.CalibreStore(lib)
	loc = "Kanakadasa/Kirtanegalu (1)"
	before = store.signature(loc, fx.ID_EPUB)
	digest = hashlib.sha1(open(os.path.join(lib, "metadata.db"), "rb").read()).hexdigest()
	con = sqlite3.connect(os.path.join(lib, "metadata.db"))
	con.execute("update books set last_modified = '2024-01-01 00:00:00+00:00' where id = 1")
	con.commit()
	con.close()
	assert calibre.CalibreStore(lib).signature(loc, fx.ID_EPUB) != before
	assert digest != hashlib.sha1(open(os.path.join(lib, "metadata.db"), "rb").read()).hexdigest()
	# reading alone leaves the file as it was
	same = hashlib.sha1(open(os.path.join(lib, "metadata.db"), "rb").read()).hexdigest()
	list(calibre.CalibreStore(lib).iter_items())
	assert same == hashlib.sha1(open(os.path.join(lib, "metadata.db"), "rb").read()).hexdigest()


def test_an_epubs_text_is_read_for_search_but_not_a_pdfs(lib):
	import os

	from sok_resdesk.tests.unit_ebooktext import make

	store = calibre.CalibreStore(lib)
	loc = "Kanakadasa/Kirtanegalu (1)"
	assert store.book_text(fx.ID_EPUB, loc) == ""  # the fixture's file is not a real EPUB: nothing, no error
	make(os.path.join(lib, loc, "Kirtanegalu - Kanakadasa.epub"))
	assert "Second" in store.book_text(fx.ID_EPUB, loc)
	assert store.book_text(fx.ID_PDF, "Smith, John/Typed notes (2)") == ""  # a PDF is read from the PDF
