"""0.62: an offline copy of a collection (a folder of web pages Kiwix can package)."""

import json
import re
import zipfile

from sok_resdesk.core import offline

BOOKS = [
	{
		"item_id": "bk/1: ವಚನ",
		"title": "Vachana <one>",
		"authors": ["Basava"],
		"year": 1950,
		"subjects": ["poetry"],
		"pages": [{"label": "1", "text": "ಜ್ಞಾನ & light"}, {"label": "2", "text": "   "}],
		"files": [("b.pdf", None)],
	},
	{"item_id": "bk2", "title": "Details only", "authors": [], "pages": [], "files": []},
]


def test_a_slug_is_safe_and_unique_where_it_changed():
	assert offline.slug("plain-id_1") == "plain-id_1"
	a, b = offline.slug("a/b"), offline.slug("a:b")
	assert a != b and "/" not in a and ":" not in b


def test_the_site_has_an_index_a_page_per_book_and_text_where_held(tmp_path):
	pdf = tmp_path / "b.pdf"
	pdf.write_bytes(b"%PDF")
	books = [dict(b, files=[(n, str(pdf)) for n, _ in b["files"]]) for b in BOOKS]
	dest = tmp_path / "site.zip"
	offline.write_zip(str(dest), books, "My <Library>", "Intro", "2026-11-06")
	z = zipfile.ZipFile(dest)
	names = z.namelist()
	assert {"index.html", "style.css", "search.js", "search-data.js", "HOW-TO-MAKE-A-ZIM.txt"} <= set(names)
	s1, s2 = books[0]["slug"], books[1]["slug"]
	assert f"books/{s1}.html" in names and f"text/{s1}.html" in names and f"files/{s1}/b.pdf" in names
	assert f"text/{s2}.html" not in names  # no text, no text page
	page = z.read(f"books/{s1}.html").decode()
	assert "Vachana &lt;one&gt;" in page and "Read the text" in page and "1 pages" in page
	assert "Only the details" in z.read(f"books/{s2}.html").decode()
	index = z.read("index.html").decode()
	assert "My &lt;Library&gt;" in index and "2 books" in index
	assert "&amp; light" in z.read(f"text/{s1}.html").decode()


def test_the_search_data_has_titles_authors_and_text_and_is_valid_script(tmp_path):
	books = [dict(b, files=[]) for b in BOOKS]
	data = "".join(c.decode() for p, c, f in offline.iter_site(books, "T", "i", "d") if p == "search-data.js")
	rows = json.loads(re.match(r"var SEARCH=(.*);$", data, re.S).group(1))
	assert rows[0]["t"].startswith("Vachana") and rows[0]["a"] == "Basava" and "ಜ್ಞಾನ" in rows[0]["x"]
	assert rows[1]["x"] == "" and rows[0]["u"].startswith("books/")


def test_a_folder_is_written_too(tmp_path):
	books = [dict(b, files=[]) for b in BOOKS]
	n = offline.write_folder(str(tmp_path / "site"), books, "T", "i", "d")
	assert n > 5 and (tmp_path / "site" / "index.html").is_file()
