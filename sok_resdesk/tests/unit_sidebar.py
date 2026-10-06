"""0.66.2: the sidebar list, and the Sidebar file Frappe 16.50 and later ship from it."""

import json
import os
import sys

from sok_resdesk.core import sidebar

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _maker():
	sys.path.insert(0, os.path.join(ROOT, "scripts"))
	import make_sidebar_json

	return make_sidebar_json


def test_the_shipped_sidebar_file_matches_the_list():
	mk = _maker()
	with open(mk.PATH, encoding="utf-8") as f:
		assert json.load(f) == mk.document(), "run: python scripts/make_sidebar_json.py"


def test_the_list_has_every_section_and_hides_what_is_off():
	items = sidebar.build()
	labels = [i["label"] for i in items]
	for label in ("Catalogue", "Exchange", "Connections", "Administration", "Portal Translations"):
		assert label in labels
	hidden = {
		t
		for e in sidebar.STRUCTURE
		if e[0] == "section"
		for c in e[3]
		for t in [c[2]]
		if c[2] == "RD Deposit"
	}
	assert "Deposits" not in [i["label"] for i in sidebar.build(hidden)]
	# a section with nothing left goes
	keeping = {c[2] for e in sidebar.STRUCTURE if e[0] == "section" and e[1] == "Keeping" for c in e[3]}
	assert "Keeping" not in [i["label"] for i in sidebar.build(keeping)]
