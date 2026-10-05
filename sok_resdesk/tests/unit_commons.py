"""0.59: a photograph for Wikimedia Commons: names, licences, the description page, depicts, upload."""

import json

import pytest

from sok_resdesk.core import commons as cm
from sok_resdesk.core import wikimedia as wm
from sok_resdesk.tests.unit_wikimedia import Session
from sok_resdesk.tests.wikisource_fixtures import Resp


def test_only_free_licences_are_accepted():
	assert cm.licence_for("https://creativecommons.org/licenses/by-sa/4.0/")[0] == "{{Cc-by-sa-4.0}}"
	assert cm.licence_for("http://creativecommons.org/publicdomain/zero/1.0/")[0] == "{{Cc-zero}}"
	assert cm.licence_for("https://creativecommons.org/licenses/by-nc/4.0/") is None
	assert cm.licence_for("https://creativecommons.org/licenses/by-nd/4.0/") is None
	assert cm.licence_problem("") and cm.licence_problem("https://example.org/all-rights-reserved")
	assert cm.licence_problem("https://creativecommons.org/licenses/by/4.0/") == ""


def test_a_file_name_is_descriptive_and_safe():
	n = cm.file_name("the ratha: at dusk [Udupi]", "jpg", "1987-03-14", "Udupi")
	assert n == "The ratha at dusk Udupi, Udupi, 1987-03-14.jpg" or n.endswith("1987-03-14.jpg")
	for bad in "#<>[]|{}:/":
		assert bad not in n
	assert cm.file_name("", "png") == "Photograph.png"
	assert len(cm.file_name("x" * 400, "jpg").encode()) <= cm.MAX_NAME_BYTES
	assert cm.clean_name("File:ratha/dusk.jpg") == "Ratha dusk.jpg"


def test_categories_and_depicts_are_read_from_the_fields():
	assert cm.split_names("category:Rathas, Udupi\nrathas") == ["Rathas", "Udupi"]
	assert cm.depicts("Q1234 Udupi Krishna Temple\nq5\nnot a q\nQ1234") == [
		("Q1234", "Udupi Krishna Temple"),
		("Q5", ""),
	]
	claims = json.loads(cm.depicts_claims(["Q1234"]))["claims"]
	assert claims[0]["mainsnak"]["property"] == "P180"
	assert claims[0]["mainsnak"]["datavalue"]["value"]["id"] == "Q1234"


def test_the_description_page_has_licence_categories_and_safe_parameters():
	page = cm.description_page(
		description="A | b = c",
		lang="kn",
		taken="1987",
		author="A. Photographer",
		source="https://lib/library/item/ph-x",
		licence="{{Cc-by-4.0}}",
		categories=["Rathas"],
		gps="13.34, 74.75",
		accession="ph-x",
	)
	assert "{{kn|1=A {{!}} b &#61; c}}" in page
	assert "{{Location|13.34|74.75}}" in page
	assert "== {{int:license-header}} ==\n{{Cc-by-4.0}}" in page
	assert page.rstrip().endswith("[[Category:Rathas]]")
	assert "{{en|1=" in cm.description_page(
		description="x", lang="", taken="", author="a", source="s", licence="{{Cc-zero}}", categories=[]
	)


def test_upload_refuses_a_warning_and_sends_the_file(tmp_path):
	f = tmp_path / "a.jpg"
	f.write_bytes(b"\xff\xd8x")
	ok = Session({"query": {"tokens": {"csrftoken": "T"}}}, {"upload": {"result": "Success"}})
	c = wm.WikimediaClient("https://commons.wikimedia.org/w/api.php", "tok", session=ok)
	assert c.upload("A.jpg", str(f), "text", "why")["result"] == "Success"
	posted = ok.asked[-1][1]
	assert posted["action"] == "upload" and posted["filename"] == "A.jpg" and posted["token"] == "T"
	dup = Session(
		{"query": {"tokens": {"csrftoken": "T"}}},
		Resp({"upload": {"result": "Warning", "warnings": {"duplicate": ["B.jpg"]}}}),
	)
	c = wm.WikimediaClient("https://commons.wikimedia.org/w/api.php", "tok", session=dup)
	with pytest.raises(wm.WikimediaError, match="duplicate"):
		c.upload("A.jpg", str(f), "text", "why")
