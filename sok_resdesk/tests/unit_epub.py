"""A book's text as EPUB 3 and plain text (core/epub.py). Pure Python: runs in CI with pytest.
(The files were also checked with W3C EPUBCheck 5.2: no errors or warnings.)"""

import io
import zipfile
from datetime import UTC, datetime

from sok_resdesk.core import epub

RECORD = {
	"item_id": "kanakadasa1950",
	"title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು",
	"creators": ["Kanakadasa", "A & B <ed>"],
	"year": "1950",
	"licence_url": "https://creativecommons.org/publicdomain/mark/1.0/",
}


def _pages(n=3, status=""):
	return [
		{
			"leaf": i,
			"label": str(i + 10) if i else "",
			"text": f"ಸಾಲು {i}\nಎರಡನೆಯ ಸಾಲು\n\nಹೊಸ & <b>\x0b",
			"status": status,
		}
		for i in range(n)
	]


def _open(data: bytes) -> zipfile.ZipFile:
	return zipfile.ZipFile(io.BytesIO(data))


def test_the_container_is_a_valid_epub_shape():
	z = _open(epub.build(RECORD, _pages(), "kn", "https://lib.example.org/library/item/x", "SOK Library"))
	first = z.infolist()[0]
	assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
	assert z.read("mimetype") == b"application/epub+zip"
	assert "EPUB/package.opf" in z.read("META-INF/container.xml").decode()
	names = set(z.namelist())
	assert {
		"EPUB/package.opf",
		"EPUB/nav.xhtml",
		"EPUB/title.xhtml",
		"EPUB/text-001.xhtml",
		"EPUB/book.css",
	} <= names


def test_language_page_numbers_and_accessibility_metadata():
	z = _open(
		epub.build(
			RECORD,
			_pages(),
			"kn",
			"https://lib.example.org/x",
			"SOK Library",
			datetime(2026, 1, 2, tzinfo=UTC),
		)
	)
	opf = z.read("EPUB/package.opf").decode()
	assert "<dc:language>kn</dc:language>" in opf
	assert '<meta property="dcterms:modified">2026-01-02T00:00:00Z</meta>' in opf
	assert "printPageNumbers" in opf and "schema:accessModeSufficient" in opf
	assert '<dc:creator id="creator2">A &amp; B &lt;ed&gt;</dc:creator>' in opf
	nav = z.read("EPUB/nav.xhtml").decode()
	assert (
		'epub:type="page-list"' in nav and ">11</a>" in nav and ">[1]</a>" in nav
	)  # no printed number: its place
	text = z.read("EPUB/text-001.xhtml").decode()
	assert 'lang="kn"' in text and 'epub:type="pagebreak"' in text and 'id="page-2"' in text
	assert "ಸಾಲು 1<br/>ಎರಡನೆಯ ಸಾಲು" in text  # verse lines kept
	assert "ಹೊಸ &amp; &lt;b&gt;" in text and "\x0b" not in text


def test_long_books_are_split_and_empty_pages_left_out():
	pages = _pages(epub.PAGES_PER_FILE + 5) + [{"leaf": 999, "label": "", "text": "   "}]
	z = _open(epub.build(RECORD, pages, "kn"))
	assert "EPUB/text-002.xhtml" in z.namelist()
	assert "page-999" not in z.read("EPUB/nav.xhtml").decode()


def test_the_summary_says_how_far_the_text_can_be_trusted():
	assert "machine-read (OCR)" in epub.summary(RECORD, _pages())
	assert "Every page was proofread" in epub.summary(RECORD, _pages(status="Proofread"))
	assert "checked by a second person" in epub.summary(RECORD, _pages(status="Validated"))
	mixed = _pages(4)
	mixed[1]["status"] = "Validated"
	assert "1 of 4 pages were proofread" in epub.summary(RECORD, mixed)


def test_plain_text():
	text = epub.plain_text(RECORD, _pages(2), "https://x")
	assert text.startswith("ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು\nKanakadasa; A & B <ed>\n1950\nhttps://x")
	assert "--- [1] ---\nಸಾಲು 0" in text and "--- 11 ---" in text
	assert "\x0b" not in text
