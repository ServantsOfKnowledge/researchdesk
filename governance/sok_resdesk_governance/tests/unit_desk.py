"""The records office's additions to the Desk: its sidebar entries land in the right place, and its Help
buttons point at real sections."""

import os
import re

from sok_resdesk.core import helpdocs
from sok_resdesk_governance.core import desk

DOCS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs")


def _items():
	return [
		{"type": "Section Break", "label": "Catalogue"},
		{"type": "Link", "label": "Items", "link_to": "RD Item"},
		{"type": "Section Break", "label": desk.SECTION},
		{"type": "Link", "label": "Background Jobs", "link_to": "resdesk-jobs"},
		{"type": "Link", "label": desk.AFTER, "link_to": "resdesk-server"},
		{"type": "Link", "label": "Open Portal", "url": "/"},
		{"type": "Section Break", "label": "Administration"},
	]


def test_entries_follow_the_server_screen():
	links = [{"type": "Link", "label": "Audit Log", "link_to": "RD Audit Event"}]
	out = desk.inserted(_items(), links)
	assert [i["label"] for i in out].index("Audit Log") == [i["label"] for i in out].index(desk.AFTER) + 1
	assert len(out) == len(_items()) + 1


def test_entries_are_not_added_twice():
	links = [{"type": "Link", "label": "Audit Log", "link_to": "RD Audit Event"}]
	once = desk.inserted(_items(), links)
	assert desk.inserted(once, links) == once


def test_without_the_server_screen_they_join_the_end_of_the_section():
	items = [i for i in _items() if i["label"] != desk.AFTER]
	out = desk.inserted(items, [{"type": "Link", "label": "Audit Log", "link_to": "RD Audit Event"}])
	assert [i["label"] for i in out].index("Audit Log") < [i["label"] for i in out].index("Administration")


def test_the_officer_roles_work_in_the_desk():
	assert set(desk.ROLES) == {"ResDesk Security Officer", "ResDesk Records Officer"}
	assert all(works for _text, works in desk.ROLES.values())


def test_help_buttons_point_at_real_headings():
	for screen, (slug, anchor) in desk.SCREEN_HELP.items():
		page = helpdocs.BY_SLUG[slug]
		with open(os.path.join(DOCS, page.file), encoding="utf-8") as f:
			assert anchor in helpdocs.anchors(f.read()), f"{screen}: {page.file} has no #{anchor}"
	assert re.fullmatch(r"RD [A-Za-z ]+", next(iter(desk.SCREEN_HELP)))
