"""What the contributors page may show (core/contributors.py)."""

from sok_resdesk.core.contributors import public_row


def test_only_agreed_fields_are_shown_and_trimmed():
	row = {
		"full_name": " Asha Rao ",
		"kind": "Individual",
		"organisation": " Mysuru Library ",
		"about": "Proofreads Kannada.",
		"access_note": "needs large print",
		"volunteer_note": "evenings",
		"staff_note": "private",
		"website": "https://example.org",
	}
	out = public_row(row)
	assert out["name"] == "Asha Rao" and out["organisation"] == "Mysuru Library"
	assert "access_note" not in out and "staff_note" not in out and "volunteer_note" not in out
	assert out["website"] == "https://example.org"


def test_odd_websites_and_nameless_profiles_are_dropped():
	assert public_row({"full_name": "A", "website": "javascript:alert(1)"})["website"] == ""
	assert public_row({"full_name": "A", "website": "https://a b"})["website"] == ""
	assert public_row({"full_name": "  "}) is None
