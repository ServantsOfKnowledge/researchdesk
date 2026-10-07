"""0.68.0: the profile form keeps only known fields, trimmed."""

import sys
import types

# profile.py imports frappe at the top; the cleaning is pure, so a stand-in is enough here
if "frappe" not in sys.modules:
	try:
		import frappe  # noqa: F401
	except ImportError:
		stub = types.ModuleType("frappe")
		stub._ = lambda s: s
		stub.whitelist = lambda *a, **k: lambda f: f
		sys.modules["frappe"] = stub
		utils = types.ModuleType("frappe.utils")
		utils.cint = lambda v: int(v or 0)
		sys.modules["frappe.utils"] = utils

from sok_resdesk import profile


def test_only_known_fields_survive_and_are_trimmed():
	out = profile.clean({"user": "x@y.z", "about": "a" * 5000, "organisation": " SOK ", "evil": 1})
	assert set(out) == {"about", "organisation"}
	assert len(out["about"]) == 1500 and out["organisation"] == "SOK"


def test_ticks_become_numbers_and_site_gets_a_scheme():
	out = profile.clean(
		{"wants_reviewer": "1", "wants_proofreader": 0, "website": "example.org", "kind": "Weird"}
	)
	assert out["wants_reviewer"] == 1 and out["wants_proofreader"] == 0
	assert out["website"] == "https://example.org" and out["kind"] == "Individual"
