"""0.52: the Calibre folder a set of books is exported as (no Frappe)."""

import csv
import io
import xml.etree.ElementTree as ET
import zipfile

from sok_resdesk.core import calibre_export as ce

BOOK = {
	"item_id": "calibre-aaaaaaaa1111",
	"uuid": ce.book_uuid("calibre-aaaaaaaa1111"),
	"title": "Kirtanegalu: songs/1",
	"authors": ["Kanakadasa", "Smith, John"],
	"date": "1931-01-01",
	"publisher": "Mysore Press",
	"language": "kan",
	"tags": ["poetry"],
	"series": "Dasa Sahitya",
	"description": "Songs & <more>",
	"identifiers": {"isbn": "9780000000002"},
}
DC = "{http://purl.org/dc/elements/1.1/}"


def test_a_name_is_safe_on_any_system():
	assert ce.clean('A/B\\C:D*E?"F<G>H|I') == "A B C D E F G H I"
	assert ce.clean("  ..  ") == "Unknown" and len(ce.clean("x" * 200)) == 60


def test_the_opf_carries_the_details_calibre_reads():
	root = ET.fromstring(ce.opf({**BOOK, "cover": "/x/cover.jpg"}))
	ns = {"dc": "http://purl.org/dc/elements/1.1/", "o": "http://www.idpf.org/2007/opf"}
	assert root.find("o:metadata/dc:title", ns).text == "Kirtanegalu: songs/1"
	assert [e.text for e in root.findall("o:metadata/dc:creator", ns)] == ["Kanakadasa", "Smith, John"]
	assert root.find("o:metadata/dc:description", ns).text == "Songs & <more>"  # escaped on the way
	assert root.find("o:metadata/dc:language", ns).text == "kan"
	ids = {
		e.get("{http://www.idpf.org/2007/opf}scheme"): e.text
		for e in root.findall("o:metadata/dc:identifier", ns)
	}
	assert ids["isbn"] == "9780000000002" and ids["uuid"] == BOOK["uuid"]
	metas = {m.get("name"): m.get("content") for m in root.findall("o:metadata/o:meta", ns)}
	assert metas["calibre:series"] == "Dasa Sahitya"
	assert root.find("o:guide/o:reference", ns).get("href") == "cover.jpg"
	assert "<guide>" not in ce.opf(BOOK)  # no cover, no cover entry


def test_a_books_uuid_is_the_same_every_time():
	assert ce.book_uuid("x") == ce.book_uuid("x") != ce.book_uuid("y")


def test_the_zip_holds_each_book_in_its_own_folder_with_its_formats_together(tmp_path):
	epub, mobi, cover = tmp_path / "a.epub", tmp_path / "a.mobi", tmp_path / "c.jpg"
	epub.write_bytes(b"EPUB")
	mobi.write_bytes(b"MOBI")
	cover.write_bytes(b"JPG")
	book = {**BOOK, "files": [("a.epub", str(epub)), ("a.mobi", str(mobi))], "cover": str(cover)}
	other = {**BOOK, "item_id": "b", "title": "Other", "files": [("x.epub", str(epub))], "cover": ""}
	left = [
		{
			"item_id": "ia-1",
			"title": "On IA",
			"authors": ["A"],
			"year": 1900,
			"why": "On archive.org",
			"link": "https://archive.org/details/ia-1",
		}
	]
	dest = str(tmp_path / "out.zip")
	assert ce.write_zip(dest, [book, other], left) == 3
	with zipfile.ZipFile(dest) as z:
		names = sorted(z.namelist())
		assert "README.txt" in names and "not-included.csv" in names
		folder = "Kanakadasa/Kirtanegalu songs 1 (1)"
		assert f"{folder}/metadata.opf" in names and f"{folder}/cover.jpg" in names
		assert f"{folder}/Kirtanegalu songs 1 - Kanakadasa.epub" in names
		assert f"{folder}/Kirtanegalu songs 1 - Kanakadasa.mobi" in names
		assert "Kanakadasa/Other (2)/Other - Kanakadasa.epub" in names
		assert z.read(f"{folder}/Kirtanegalu songs 1 - Kanakadasa.epub") == b"EPUB"
		rows = list(csv.DictReader(io.StringIO(z.read("not-included.csv").decode())))
		assert rows[0]["identifier"] == "ia-1" and rows[0]["where it is"].startswith("https://archive.org")
	assert ce.total_size([book]) == 4 + 4 + 3


def test_two_files_of_one_format_both_stay(tmp_path):
	a, b = tmp_path / "1.pdf", tmp_path / "2.pdf"
	a.write_bytes(b"A")
	b.write_bytes(b"B")
	dest = str(tmp_path / "o.zip")
	ce.write_zip(dest, [{**BOOK, "files": [("1.pdf", str(a)), ("2.pdf", str(b))], "cover": ""}])
	with zipfile.ZipFile(dest) as z:
		assert len([n for n in z.namelist() if n.endswith(".pdf")]) == 2
