"""Zones for OCR (core/zones.py). Pure Python."""

import pytest

from sok_resdesk.core import zones as zn


def test_zones_stay_on_the_page_and_slips_are_refused():
	z = zn.zone(90, -5, 30, 20)
	assert z == {"x": 90, "y": 0, "w": 10, "h": 20, "kind": "text"}
	with pytest.raises(zn.ZoneError):
		zn.zone(10, 10, 0.5, 30)
	with pytest.raises(zn.ZoneError):
		zn.zone(10, 10, 30, 30, kind="picture")
	assert zn.clean('[{"x":1,"y":2,"w":30,"h":40,"kind":"skip"}]')[0]["kind"] == "skip"
	assert len(zn.clean([{"x": 0, "y": 0, "w": 10, "h": 10}] * 99)) == 40


def test_presets():
	p = zn.presets()
	assert len(p["Two columns"]) == 2 and len(p["Three columns"]) == 3
	left, right = p["Two columns"]
	assert left["x"] < right["x"] and left["x"] + left["w"] <= right["x"] + 0.01
	heading = p["Heading and two columns"][0]
	assert heading["w"] > 90 and heading["y"] < p["Heading and two columns"][1]["y"]


def test_reading_order_columns_under_headings():
	heading = zn.zone(2, 2, 96, 10)
	left_top, left_bottom = zn.zone(2, 15, 46, 30), zn.zone(2, 50, 46, 40)
	right_top = zn.zone(52, 15, 46, 75)
	footer = zn.zone(2, 92, 96, 6)
	shuffled = [right_top, footer, left_bottom, heading, left_top]
	assert zn.in_reading_order(shuffled) == [heading, left_top, left_bottom, right_top, footer]


def test_pixels_and_join():
	assert zn.pixels(zn.zone(10, 20, 30, 40), 1000, 2000) == (100, 400, 400, 1200)
	# a zone at the very edge still crops at least one pixel (an empty crop would break OCR)
	assert zn.pixels({"x": 99.9, "y": 99.9, "w": 0.1, "h": 0.1}, 10, 10) == (9, 9, 10, 10)
	assert zn.join(["  ಮೊದಲು ", "", "second\n"]) == "ಮೊದಲು\n\nsecond"
