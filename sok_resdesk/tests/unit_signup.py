"""What the join page accepts."""

from sok_resdesk.core import signup


def test_a_good_form_is_cleaned():
	fields, why = signup.clean(" Asha  <b>K</b> ", " Asha@Example.ORG ", "longenough1")
	assert why == ""
	assert fields == {"full_name": "Asha K", "email": "asha@example.org", "password": "longenough1"}


def test_each_problem_has_its_own_answer():
	assert signup.clean("", "a@b.co", "longenough1")[1] == "name"
	assert signup.clean("<br>", "a@b.co", "longenough1")[1] == "name"
	for bad in ("", "nobody", "a@b", "a b@c.de", "@c.de", "a" * 200 + "@c.de"):
		assert signup.clean("Asha", bad, "longenough1")[1] == "email", bad
	assert signup.clean("Asha", "a@b.co", "short")[1] == "password"
	assert signup.clean("Asha", "a@b.co", "")[1] == "password"


def test_a_filled_hidden_field_is_a_robot():
	assert signup.clean("Asha", "a@b.co", "longenough1", trap="http://x")[1] == "trap"


def test_the_password_is_kept_exactly_as_typed():
	fields, _ = signup.clean("Asha", "a@b.co", "  spaces kept  ")
	assert fields["password"] == "  spaces kept  "


def test_only_a_plain_path_on_this_site_is_gone_to_afterwards():
	for ok in ("/library", "/library/item/abc-1.2", "/library/item/x?page=3&view=text", "/"):
		assert signup.safe_next(ok) == ok
	for bad in (
		"",
		None,
		"https://evil.example",
		"//evil.example",
		"/\t/evil.example",
		"/\n/evil.example",
		"/ /evil.example",
		"/\\evil.example",
		"javascript:alert(1)",
		"/library?x=<script>",
	):
		assert signup.safe_next(bad) == "/library", repr(bad)
