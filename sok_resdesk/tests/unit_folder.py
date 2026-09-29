"""Unit tests for IA-style item folders on disk and over HTTP (no Frappe, no internet).

Named unit_*.py (not test_*) so Frappe's test runner, which has no pytest, skips it. Run: pytest
"""

import functools
import gzip
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sok_resdesk.core.folder import (
	FolderStore,
	HttpStore,
	StoreError,
	pages_from_djvu_xml,
	pages_from_hocr,
	parse_meta_xml,
)

META = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <identifier>{id}</identifier>
  <title>ವಚನ ಸಂಗ್ರಹ</title>
  <creator>ಬಸವಣ್ಣ</creator>
  <collection>ServantsOfKnowledge</collection>
  <collection>JaiGyan</collection>
  <language>Kan</language>
  <date>1935</date>
  <imagecount>3</imagecount>
</metadata>"""

HOCR = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta name="ocr-system" content="tesseract" /></head><body>
<div class="ocr_page" id="page_000000"></div>
<div class="ocr_page" id="page_000001"><div class="ocr_carea"><p class="ocr_par">
<span class="ocr_line"><span class="ocrx_word">ಕಳಬೇಡ</span> <span class="ocrx_word">ಕೊಲಬೇಡ</span></span>
<span class="ocr_line"><span class="ocrx_word">ಹುಸಿಯ</span> <span class="ocrx_word">&amp;ನುಡಿಯಲು</span></span>
</p></div></div>
<div class="ocr_page" id="page_000002"><span class="ocr_line"><span class="ocrx_word">ಮುನಿಯಬೇಡ</span></span></div>
</body></html>"""

CHOCR = """<html><body>
<div class="ocr_page"><span class="ocr_line"><span class="ocrx_word">
<span class="ocrx_cinfo">ಅ</span>
<span class="ocrx_cinfo">ನ್ಯ</span></span>
<span class="ocrx_word"><span class="ocrx_cinfo">ರಿ</span><span class="ocrx_cinfo">ಗೆ</span></span></span></div>
</body></html>"""

DJVU = """<?xml version="1.0" encoding="UTF-8"?>
<DjVuXML><BODY>
<OBJECT data="x"><HIDDENTEXT/></OBJECT>
<OBJECT data="x"><HIDDENTEXT><PAGECOLUMN><REGION><PARAGRAPH>
<LINE><WORD coords="1">ಅಸಹ್ಯಪಡಬೇಡ</WORD><WORD coords="2">ಇದಿರ</WORD></LINE>
<LINE><WORD coords="3">ಹಳಿಯಲು</WORD></LINE>
</PARAGRAPH></REGION></PAGECOLUMN></HIDDENTEXT></OBJECT>
</BODY></DjVuXML>"""


def make_item(root, rel, ident, kind):
	d = root / rel
	d.mkdir(parents=True)
	(d / f"{ident}_meta.xml").write_text(META.format(id=ident), encoding="utf-8")
	(d / f"{ident}.pdf").write_bytes(b"%PDF-1.4 test")
	if kind == "searchtext":
		text = "ಮೊದಲ ಪುಟ\nಎರಡನೇ ಪುಟ"
		(d / f"{ident}_hocr_searchtext.txt.gz").write_bytes(gzip.compress(text.encode()))
		(d / f"{ident}_hocr_pageindex.json.gz").write_bytes(gzip.compress(json.dumps([[0, 0, 0, 0], [0, 8, 0, 0], [9, 19, 0, 0]]).encode()))
		(d / f"{ident}_page_numbers.json").write_text(json.dumps({"pages": [{"pageNumber": ""}, {"pageNumber": "1"}, {"pageNumber": "2"}]}))
		(d / "__ia_thumb.jpg").write_bytes(b"\xff\xd8thumb")
	elif kind == "hocr":
		(d / f"{ident}_hocr.html").write_text(HOCR, encoding="utf-8")
	elif kind == "chocr":
		(d / f"{ident}_chocr.html.gz").write_bytes(gzip.compress(CHOCR.encode()))
	elif kind == "djvu":
		(d / f"{ident}_djvu.xml").write_text(DJVU, encoding="utf-8")
	elif kind == "txt":
		(d / f"{ident}_djvu.txt").write_text("ಪಠ್ಯ " * 2000, encoding="utf-8")
	return d


@pytest.fixture
def library(tmp_path):
	make_item(tmp_path, "a0001", "a0001", "searchtext")
	make_item(tmp_path, "2026/sep/b0002", "b0002", "hocr")
	make_item(tmp_path, "c0003", "c0003", "chocr")
	make_item(tmp_path, "deep/x/y/d0004", "d0004", "djvu")
	make_item(tmp_path, "e0005", "e0005", "txt")
	(tmp_path / "notes").mkdir()
	(tmp_path / "notes" / "readme.txt").write_text("not an item")
	return tmp_path


def test_meta_xml_repeated_tags_become_lists():
	meta = parse_meta_xml(META.format(id="x").encode())
	assert meta["identifier"] == "x"
	assert meta["collection"] == ["ServantsOfKnowledge", "JaiGyan"]
	assert meta["language"] == "Kan"
	with pytest.raises(StoreError):
		parse_meta_xml(b"<not-xml")


def test_hocr_and_chocr_and_djvu_parsers():
	pages = pages_from_hocr(HOCR.encode())
	assert [p["leaf"] for p in pages] == [1, 2]
	assert pages[0]["text"] == "ಕಳಬೇಡ ಕೊಲಬೇಡ\nಹುಸಿಯ &ನುಡಿಯಲು"
	assert pages_from_hocr(CHOCR.encode())[0]["text"] == "ಅನ್ಯ ರಿಗೆ"
	dj = pages_from_djvu_xml(DJVU.encode())
	assert dj == [{"leaf": 1, "label": "", "text": "ಅಸಹ್ಯಪಡಬೇಡ ಇದಿರ\nಹಳಿಯಲು"}]


def test_folder_store_finds_nested_items(library):
	store = FolderStore(str(library))
	items = dict(store.iter_items())
	assert items == {
		"a0001": "a0001", "b0002": "2026/sep/b0002", "c0003": "c0003", "d0004": "deep/x/y/d0004", "e0005": "e0005",
	}
	assert len(list(store.iter_items(limit=2))) == 2


def test_folder_store_text_priority(library):
	store = FolderStore(str(library))
	data = store.load_item("a0001", "a0001")
	pages, src = store.page_texts("a0001", "a0001", data["page_numbers"])
	assert src == "hocr_searchtext" and [(p["leaf"], p["label"]) for p in pages] == [(1, "1"), (2, "2")]
	assert store.page_texts("b0002", "2026/sep/b0002")[1] == "hocr.html"
	assert store.page_texts("c0003", "c0003")[1] == "chocr.html.gz"
	assert store.page_texts("d0004", "deep/x/y/d0004")[1] == "djvu.xml"
	assert store.page_texts("e0005", "e0005") == ([], "")
	assert len(store.book_text("e0005", "e0005")) > 5000
	assert store.pdf_name("a0001", "a0001") == "a0001.pdf"
	assert store.thumb_name("a0001") == "__ia_thumb.jpg"


def test_folder_store_signature_changes_and_blocks_traversal(library):
	store = FolderStore(str(library))
	before = store.signature("a0001", "a0001")
	meta = library / "a0001" / "a0001_meta.xml"
	meta.write_text(META.format(id="a0001").replace("1935", "1936"), encoding="utf-8")
	import os
	os.utime(meta, (1, 2_000_000_000))
	assert store.signature("a0001", "a0001") != before
	with pytest.raises(StoreError):
		store.read("../..", "etc/passwd")
	with pytest.raises(StoreError):
		FolderStore(str(library / "missing"))


@pytest.fixture
def http_library(library):
	handler = functools.partial(SimpleHTTPRequestHandler, directory=str(library))
	handler.log_message = lambda *a, **k: None
	server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	yield f"http://127.0.0.1:{server.server_address[1]}/", library
	server.shutdown()


def test_http_store_crawls_directory_listing(http_library):
	base, _ = http_library
	store = HttpStore(base)
	store.session.trust_env = False
	items = dict(store.iter_items())
	assert set(items) == {"a0001", "b0002", "c0003", "d0004", "e0005"}
	data = store.load_item("a0001", items["a0001"])
	assert data["metadata"]["title"] == "ವಚನ ಸಂಗ್ರಹ"
	pages, src = store.page_texts("a0001", "a0001", data["page_numbers"])
	assert src == "hocr_searchtext" and len(pages) == 2
	assert store.public_url("a0001", "a0001.pdf") == f"{base}a0001/a0001.pdf"


def test_http_store_manifest(http_library):
	base, library = http_library
	(library / "identifiers.txt").write_text("# books\na0001\n2026/sep/b0002\n")
	store = HttpStore(base, manifest_url=f"{base}identifiers.txt")
	store.session.trust_env = False
	assert list(store.iter_items()) == [("a0001", "a0001"), ("b0002", "2026/sep/b0002")]
	assert store.page_texts("b0002", "2026/sep/b0002")[1] == "hocr.html"
