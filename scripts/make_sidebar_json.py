"""Write the Sidebar Frappe 16.50 and later ship for Research Desk, from core/sidebar.py.

Run after changing the list: python scripts/make_sidebar_json.py. A unit test checks the file
matches the list, so the two cannot drift.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sok_resdesk.core import sidebar  # noqa: E402

PATH = os.path.join(
	os.path.dirname(__file__),
	"..",
	"sok_resdesk",
	"resdesk",
	"sidebar",
	"research_desk",
	"research_desk.json",
)
ITEM_DEFAULTS = {
	"added": 0,
	"child": 0,
	"collapsible": 1,
	"hidden": 0,
	"icon": "",
	"indent": 0,
	"is_default_module": 0,
	"keep_closed": 0,
	"open_in_new_tab": 0,
	"show_arrow": 0,
}


def modified() -> str:
	"""Frappe re-reads a shipped file only when its `modified` is newer than the site's copy, so it must
	grow with every release (a fixed date left a new menu entry out of an upgraded site)."""
	from datetime import datetime, timedelta

	from sok_resdesk import __version__

	major, minor, patch = (list(map(int, __version__.split("."))) + [0, 0])[:3]
	when = datetime(2026, 11, 6, 12) + timedelta(minutes=(major * 1000 + minor) * 100 + patch)
	return when.strftime("%Y-%m-%d %H:%M:%S.000000")


def document() -> dict:
	rows = []
	for it in sidebar.build():
		row = {**ITEM_DEFAULTS, **it}
		if it.get("link_type") == "URL":
			row["link_type"] = ""
		rows.append(dict(sorted(row.items())))
	return {
		"app": "sok_resdesk",
		"creation": "2026-11-06 12:00:00.000000",
		"docstatus": 0,
		"doctype": "Sidebar",
		"header_icon": "book",
		"idx": 0,
		"items": rows,
		"modified": modified(),
		"module": "ResDesk",
		"name": sidebar.TITLE,
		"standard": 1,
		"title": sidebar.TITLE,
	}


def main() -> None:
	os.makedirs(os.path.dirname(PATH), exist_ok=True)
	with open(PATH, "w", encoding="utf-8") as f:
		json.dump(document(), f, indent=1, ensure_ascii=False)
		f.write("\n")
	print(os.path.normpath(PATH))


if __name__ == "__main__":
	main()
