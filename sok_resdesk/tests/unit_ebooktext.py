"""0.61: text from an EPUB, so a Calibre library's books can be searched."""

import zipfile

from sok_resdesk.core import ebooktext as epub

CONTAINER = (
	'<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
	'<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
)
OPF = (
	'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><manifest>'
	'<item id="a" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
	'<item id="b" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>'
	'<item id="css" href="s.css" media-type="text/css"/></manifest>'
	'<spine><itemref idref="b"/><itemref idref="a"/></spine></package>'
)


def make(path, **extra):
	with zipfile.ZipFile(path, "w") as z:
		z.writestr("META-INF/container.xml", CONTAINER)
		z.writestr("OEBPS/content.opf", OPF)
		z.writestr(
			"OEBPS/ch1.xhtml",
			"<html><head><title>T</title><style>p{}</style></head><body><h1>One</h1><p>First &amp; chapter.</p></body></html>",
		)
		z.writestr(
			"OEBPS/text/ch2.xhtml",
			"<html><body><p>ಕನ್ನಡ ಪಠ್ಯ</p><script>x()</script><p>Second</p></body></html>",
		)
		for k, v in extra.items():
			z.writestr(k, v)


def test_the_text_comes_in_reading_order_without_markup(tmp_path):
	p = tmp_path / "b.epub"
	make(p)
	text = epub.epub_text(str(p))
	assert text.index("ಕನ್ನಡ ಪಠ್ಯ") < text.index("First & chapter.")  # the spine says ch2 first
	assert "x()" not in text and "<p>" not in text and "T\n" not in text.split("\n\n")[0]
	assert "One" in text


def test_a_broken_or_foreign_file_gives_nothing(tmp_path):
	bad = tmp_path / "bad.epub"
	bad.write_bytes(b"not a zip")
	assert epub.epub_text(str(bad)) == ""
	empty = tmp_path / "e.epub"
	with zipfile.ZipFile(empty, "w") as z:
		z.writestr("x.txt", "hi")
	assert epub.epub_text(str(empty)) == ""
	assert epub.file_text(str(tmp_path / "a.mobi")) == ""


def test_plain_and_html_files_are_read_too(tmp_path):
	t = tmp_path / "a.txt"
	t.write_text("plain words", encoding="utf-8")
	h = tmp_path / "a.html"
	h.write_text("<p>one</p><p>two</p>", encoding="utf-8")
	assert epub.file_text(str(t)) == "plain words"
	assert epub.file_text(str(h)) == "one\n\ntwo"


def test_html_text_drops_scripts_and_keeps_lines():
	assert epub.html_text("<div>a<br>b</div><style>x</style><p>c</p>") == "a\nb\n\nc"
