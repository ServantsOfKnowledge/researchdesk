"""Ingest from a metadata file (core/metadump.py): every format a library is likely to have."""

import gzip
import json

import pytest

from sok_resdesk.core import metadump as md

SEARCH_LINES = (
	'{"identifier": "kanakadasa1950", "title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು", "creator": ["Kanakadasa"], "language": "kan", "imagecount": 120}\n'
	'{"identifier": "purandara1940", "title": "Purandara", "format": ["OCR Search Text"]}\n'
	"not json\n"
	'{"title": "no identifier"}\n'
)


def test_ia_search_json_lines():
	d = md.read(SEARCH_LINES.encode(), "books.jsonl")
	assert d["kind"] == "jsonl" and d["bad"] == 2 and d["complete"] == 0
	assert [r["identifier"] for r in d["rows"]] == ["kanakadasa1950", "purandara1940"]
	assert d["rows"][0]["imagecount"] == 120


def test_gzip_and_ia_metadata_records_with_files():
	line = json.dumps(
		{
			"metadata": {"identifier": "x1950", "title": "X"},
			"files": [{"name": "x1950_hocr_searchtext.txt.gz"}],
		}
	)
	d = md.read(gzip.compress((line + "\n").encode()), "full.jsonl.gz")
	assert d["complete"] == 1 and d["rows"][0]["_files"][0]["name"].endswith("searchtext.txt.gz")
	assert md.read(("[" + line + "]").encode())["kind"] == "json"


def test_csv_with_ia_columns_and_lists():
	csv = "identifier,title,subject[0],subject[1],creator,language\nkanaka1,Kanaka,Haridasa,Music,A; B,kan\n,missing id,,,,\n"
	d = md.read(csv.encode(), "export.csv")
	assert d["kind"] == "csv" and d["bad"] == 1
	row = d["rows"][0]
	assert (
		row["subject"] == ["Haridasa", "Music"] and row["creator"] == ["A", "B"] and row["language"] == "kan"
	)
	tsv = "identifier\ttitle\nk2\tTwo\n"
	assert md.read(tsv.encode(), "e.tsv")["rows"] == [{"identifier": "k2", "title": "Two"}]


def test_a_list_of_identifiers():
	d = md.read(b"# SOK Kannada\nkanaka1\nkanaka2  extra words\nbad/id\n\nkanaka1\n", "ids.txt")
	assert d["kind"] == "identifiers" and [r["identifier"] for r in d["rows"]] == ["kanaka1", "kanaka2"]
	assert d["bad"] == 1 and md.only_identifiers(d["rows"][0])


def test_the_last_record_of_a_book_wins():
	d = md.read(b'{"identifier": "a1", "title": "old"}\n{"identifier": "a1", "title": "new"}\n', "x.jsonl")
	assert d["rows"] == [{"identifier": "a1", "title": "new"}]


@pytest.mark.parametrize("data", [b"", b"   ", b"[not json"])
def test_unreadable_files_say_so(data):
	with pytest.raises(md.DumpError):
		md.read(data, "x.json")
