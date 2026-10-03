"""Catalogue first: archive.org's search records in bulk (core/ia.py), as `ia search -f` gets them."""

import pytest

from sok_resdesk.core import ia
from sok_resdesk.core.normalize import normalize_ia_item


class FakeResponse:
	def __init__(self, data, status=200):
		self._data, self.status_code, self.text = data, status, str(data)

	def json(self):
		return self._data


class FakeSession:
	"""Two pages of results joined by a cursor; refuses unknown fields like the scrape API."""

	def __init__(self, refuse=""):
		self.headers, self.calls, self.refuse = {}, [], refuse

	def get(self, url, params=None, timeout=None, **kw):
		self.calls.append(dict(params or {}))
		if self.refuse and self.refuse in params.get("fields", ""):
			return FakeResponse({"error": f"invalid field {self.refuse}"})
		if params.get("cursor") is None:
			return FakeResponse(
				{
					"items": [{"identifier": "a", "title": "A", "format": ["OCR Search Text", "Text PDF"]}],
					"cursor": "c1",
					"total": 2,
				}
			)
		return FakeResponse(
			{"items": [{"identifier": "b", "title": "B", "description": "x" * 9000}], "total": 2}
		)


def test_records_come_in_bulk_with_their_fields():
	s = FakeSession()
	client = ia.IAClient(delay=0, session=s)
	rows = list(client.iter_records("collection:x"))
	assert [r["identifier"] for r in rows] == ["a", "b"]
	assert len(s.calls) == 2 and s.calls[0]["count"] == 5000 and "imagecount" in s.calls[0]["fields"]
	assert len(rows[1]["description"]) == 2000  # long descriptions are cut on the way in
	assert list(client.iter_records("collection:x", limit=1)) == [rows[0]]


def test_a_refused_field_is_an_error_the_planner_falls_back_from():
	client = ia.IAClient(delay=0, session=FakeSession(refuse="identifier-ark"))
	with pytest.raises(ia.IAError):
		list(client.iter_records("collection:x"))
	assert [
		r["identifier"] for r in client.iter_records("collection:x", fields=ia.CATALOGUE_FIELDS_CORE)
	] == ["a", "b"]


def test_formats_say_whether_a_book_has_page_text():
	files = ia.files_from_formats("a", ["OCR Search Text", "Text PDF"])
	record = normalize_ia_item("a", {"title": "A", "language": "kan", "imagecount": "120"}, files)
	assert record["has_page_text"] and record["has_fulltext"] and record["page_count"] == 120
	assert not normalize_ia_item("b", {"title": "B"}, ia.files_from_formats("b", "Text PDF"))["has_page_text"]
	assert ia.files_from_formats("c", None) == []
