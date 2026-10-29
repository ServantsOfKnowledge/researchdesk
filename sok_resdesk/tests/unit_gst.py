"""GST arithmetic (core/gst.py), pure."""

import pytest

from sok_resdesk.core import gst

GOOD = "27AAPFU0939F1ZV"


def test_gstin_checks():
	assert gst.valid_gstin(GOOD)
	assert gst.valid_gstin(" " + GOOD.lower() + " ")
	assert not gst.valid_gstin(GOOD[:-1] + "A")  # wrong check character
	assert not gst.valid_gstin("27AAPFU0939F1Z")  # short
	assert not gst.valid_gstin("") and not gst.valid_gstin(None)
	assert gst.state_of(GOOD) == "27" and gst.state_of("nope") == ""


def _with_check(body: str) -> str:
	total = 0
	for i, c in enumerate(body):
		v = gst._CHARS.index(c) * (1 if i % 2 == 0 else 2)
		total += v // 36 + v % 36
	return body + gst._CHARS[(36 - total % 36) % 36]


def test_supply_is_decided_by_state_code():
	karnataka = _with_check("29AABCT1332L1Z")
	assert gst.valid_gstin(karnataka)
	assert gst.supply(karnataka, karnataka) == "intra"
	assert gst.supply(karnataka, GOOD) == "inter"
	assert gst.supply("", GOOD) == "" and gst.supply(karnataka, "bad") == ""


def test_line_rounds_to_the_paisa():
	assert gst.line(3, 99.99, "12") == (gst._paise("299.97"), gst._paise("36.00"))  # 35.9964
	with pytest.raises(ValueError):
		gst.line(1, 100, "7")


def test_split_always_adds_back_to_the_tax():
	lines = [(1, "33.33", "5"), (1, "10.10", "5")]  # tax 1.67 + 0.51 = 2.18
	intra = gst.totals(lines, "intra")
	assert intra["cgst"] + intra["sgst"] == pytest.approx(intra["tax"]) and intra["igst"] == 0
	inter = gst.totals(lines, "inter")
	assert inter["igst"] == inter["tax"] and inter["cgst"] == inter["sgst"] == 0
	assert inter["total"] == pytest.approx(inter["taxable"] + inter["tax"])
	unknown = gst.totals(lines, "")
	assert unknown["tax"] == inter["tax"] and unknown["cgst"] == unknown["igst"] == 0


def test_books_are_nil_rated_by_choice():
	assert gst.totals([(2, 250, "0")], "intra")["total"] == 500.0
