"""Which OCR page goes with which page image (core/scandata.py)."""

import gzip
import io
import json
import zipfile

from sok_resdesk.core import scandata
from sok_resdesk.core.folder import pages_from_hocr, pages_from_searchtext

# a colour card first and a blank cover last, left out of the book as readers see it
SCAN = b"""<?xml version="1.0"?><book><bookData><leafCount>5</leafCount></bookData><pageData>
<page leafNum="0"><pageType>Color Card</pageType><addToAccessFormats>false</addToAccessFormats></page>
<page leafNum="1"><pageType>Title</pageType><addToAccessFormats>true</addToAccessFormats></page>
<page leafNum="2"><pageType>Normal</pageType><addToAccessFormats>true</addToAccessFormats></page>
<page leafNum="3"><pageType>Normal</pageType></page>
<page leafNum="4"><pageType>Cover</pageType><addToAccessFormats>false</addToAccessFormats></page>
</pageData></book>"""
TEXTS = ["colour card", "TITLE", "page one", "page two", "cover"]


def test_parse_and_zip():
	leaves = scandata.parse(SCAN)
	assert leaves == [(0, False), (1, True), (2, True), (3, True), (4, False)]
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as z:
		z.writestr("scandata.xml", SCAN)
	assert scandata.parse(scandata.from_zip(buf.getvalue())) == leaves
	assert scandata.parse(b"<not xml") == []
	assert scandata.file_name("abc", ["abc.pdf", "abc_scandata.xml"]) == "abc_scandata.xml"
	assert scandata.file_name("abc", ["scandata.zip"]) == "scandata.zip"
	assert scandata.file_name("abc", ["abc.pdf"]) == ""


def test_text_goes_with_the_page_shown():
	pages = scandata.pages(TEXTS, None, scandata.parse(SCAN))
	# n0.jpg is the title page: its text, not the colour card's; the leaves left out lose theirs
	assert [(p["leaf"], p["text"]) for p in pages] == [(0, "TITLE"), (1, "page one"), (2, "page two")]


def test_no_mapping_when_the_ocr_already_counts_pages_shown_or_nothing_is_left_out():
	leaves = scandata.parse(SCAN)
	assert scandata.leaf_map(leaves, 3) is None  # OCR of the pages shown only
	assert scandata.leaf_map([(0, True), (1, True)], 2) is None
	assert scandata.leaf_map([], 5) is None
	assert [p["leaf"] for p in scandata.pages(["a", "", "c"], None, [])] == [0, 2]


def test_printed_numbers_follow_their_leaf():
	leaves = scandata.parse(SCAN)
	numbers = {"pages": [{"leafNum": 2, "pageNumber": "1"}, {"leafNum": 3, "pageNumber": "2"}]}
	pages = scandata.pages(TEXTS, numbers, leaves)
	assert [(p["leaf"], p["label"]) for p in pages] == [(0, ""), (1, "1"), (2, "2")]
	# without leaf numbers: in OCR page order, as before
	plain = {"pages": [{"pageNumber": ""}, {"pageNumber": ""}, {"pageNumber": "1"}]}
	assert scandata.pages(TEXTS, plain, leaves)[1]["label"] == "1"


def test_folder_formats_use_the_scan_data():
	text = "".join(TEXTS)
	index, at = [], 0
	for t in TEXTS:
		index.append([at, at + len(t), 0, 0])
		at += len(t)
	pages = pages_from_searchtext(
		gzip.compress(text.encode()), gzip.compress(json.dumps(index).encode()), None, scandata.parse(SCAN)
	)
	assert pages[0] == {"leaf": 0, "label": "", "text": "TITLE"}
	hocr = "".join(
		f"<div class='ocr_page'><span class='ocr_line'><span class='ocrx_word'>{t}</span></span></div>"
		for t in ["card", "Title", "One"]
	)
	leaves = [(0, False), (1, True), (2, True)]
	assert [(p["leaf"], p["text"]) for p in pages_from_hocr(hocr.encode(), None, leaves)] == [
		(0, "Title"),
		(1, "One"),
	]
