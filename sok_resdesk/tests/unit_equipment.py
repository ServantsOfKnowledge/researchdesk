"""What the server has (core/equipment.py)."""

import sys

from sok_resdesk.core import equipment as eq


def test_versions():
	assert eq.version_tuple("10.11.6-MariaDB-0ubuntu0.24.04.1") == (10, 11, 6)
	assert eq.version_tuple("tesseract 5.3.4") == (5, 3, 4)
	assert eq.version_tuple("") == ()
	assert eq.at_least("1.54.1", "1.11")
	assert not eq.at_least("1.9.0", "1.11")  # numbers, not text: 9 < 11
	assert eq.at_least("16.0", "16")
	assert not eq.at_least("", "1.0")


def test_programs_and_packages():
	found = eq.program("python3")
	assert found["path"] and found["version"].startswith(f"{sys.version_info[0]}.")
	assert eq.program("no-such-program-here") == {}
	assert eq.package("pytest")
	assert eq.package("no-such-package-here") is None


def test_summary():
	items = [
		eq.item("a", "Core", "A", "x", "ok"),
		eq.item("b", "Core", "B", "x", "missing"),
		eq.item("c", "Core", "C", "x", "old"),
		eq.item("d", "Core", "D", "x", "warn"),
		eq.item("e", "Core", "E", "x", "off"),
	]
	assert eq.summary(items) == {"ok": 1, "missing": 2, "warn": 1}
