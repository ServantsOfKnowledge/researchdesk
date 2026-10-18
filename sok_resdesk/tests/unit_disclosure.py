import io
from datetime import date

import pytest

from sok_resdesk.core.disclosure import box_ok, due_on, problems

PIL = pytest.importorskip("PIL")


def test_the_reply_is_owed_after_the_set_days_and_never_the_same_day():
	assert due_on(date(2026, 1, 1), 30) == date(2026, 1, 31)
	assert due_on(date(2026, 1, 1), 0) == date(2026, 1, 2)


def test_a_box_must_lie_on_the_page():
	assert box_ok(10, 10, 50, 20)
	assert not box_ok(60, 10, 50, 20)
	assert not box_ok(-1, 0, 10, 10)
	assert not box_ok(10, 10, 0, 5)
	assert not box_ok("x", 1, 1, 1)


def rec(item, decision, ground=""):
	return {"item": item, "decision": decision, "ground": ground}


BOX = {"item": "a", "page": 2, "left": 10, "top": 10, "width": 30, "height": 5}


def test_complete_decisions_have_no_problems():
	assert problems([rec("a", "Disclose redacted", "s.8(1)(j)"), rec("b", "Disclose")], [BOX]) == []


def test_withholding_or_covering_needs_a_ground():
	assert any("ground" in p for p in problems([rec("a", "Withhold")], []))
	assert any("ground" in p for p in problems([rec("a", "Disclose redacted")], [BOX]))


def test_redacted_needs_boxes_and_boxes_need_redacted():
	assert any("nothing is covered" in p for p in problems([rec("a", "Disclose redacted", "g")], []))
	assert any("not set to Disclose redacted" in p for p in problems([rec("a", "Disclose")], [BOX]))
	assert any("not set to Disclose redacted" in p for p in problems([], [BOX]))


def test_an_undecided_or_repeated_record_is_a_problem():
	assert any("no decision" in p for p in problems([rec("a", "")], []))
	assert any("twice" in p for p in problems([rec("a", "Disclose"), rec("a", "Disclose")], []))


def test_a_box_off_the_page_is_a_problem():
	bad = {**BOX, "left": 90}
	assert any("wholly on the page" in p for p in problems([rec("a", "Disclose redacted", "g")], [bad]))


def test_burned_pixels_are_black_and_the_rest_is_untouched():
	from PIL import Image

	from sok_resdesk.core.redact import burn, pdf_of

	src = io.BytesIO()
	Image.new("RGB", (100, 100), (255, 255, 255)).save(src, "PNG")
	out = Image.open(io.BytesIO(burn(src.getvalue(), [BOX])))
	assert out.getpixel((20, 12)) == (0, 0, 0)
	assert out.getpixel((80, 80)) == (255, 255, 255)
	import tempfile

	with tempfile.TemporaryDirectory() as tmp:
		path = tmp + "/p.png"
		open(path, "wb").write(burn(src.getvalue(), [BOX]))
		pdf = pdf_of([path], 100)
	assert pdf.startswith(b"%PDF")


def test_a_box_on_a_page_the_record_lacks_is_found():
	from sok_resdesk.core.disclosure import pages_off

	assert pages_off([{"item": "a", "page": 3}], {"a": 10}) == []
	assert pages_off([{"item": "a", "page": 11}], {"a": 10})
	assert pages_off([{"item": "b", "page": 1}], {})
