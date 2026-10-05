"""0.54: leaf labels for manuscripts and palm-leaf bundles (no Frappe)."""

from sok_resdesk.core import iiif, leaves
from sok_resdesk.tests.unit_iiif import BASE, BOOK, make


def test_a_b_sides_two_images_to_a_leaf():
	assert leaves.labels(6) == {0: "1a", 1: "1b", 2: "2a", 3: "2b", 4: "3a", 5: "3b"}


def test_recto_verso_and_plain_numbers():
	assert [leaves.labels(4, sides="r/v")[i] for i in range(4)] == ["1r", "1v", "2r", "2v"]
	assert leaves.labels(3, sides="none") == {0: "1", 1: "2", 2: "3"}


def test_images_before_and_after_the_leaves_are_named_as_such():
	got = leaves.labels(8, start_image=3, leaves=4)
	assert got == {0: "front 1", 1: "front 2", 2: "1a", 3: "1b", 4: "2a", 5: "2b", 6: "end 1", 7: "end 2"}


def test_the_first_leaf_can_have_any_number():
	assert leaves.labels(2, start_folio=12) == {0: "12a", 1: "12b"}


def test_odd_input_stays_inside_the_book():
	assert leaves.labels(0) == {}
	assert leaves.labels(3, start_image=99)[2] == "1a"  # the last image at most
	assert len(leaves.labels(5, start_image=2, leaves=100)) == 5


def test_stored_labels_are_read_back_whatever_their_keys():
	assert leaves.clean('{"0": "1a", "2": "2a", "x": "bad"}') == {0: "1a", 2: "2a"}
	assert leaves.clean("not json") == {} and leaves.clean(None) == {}
	assert leaves.clean({"1": "a" * 50})[1] == "a" * 20


def test_the_manifest_names_its_canvases_by_leaf_and_describes_the_manuscript():
	book = {
		**BOOK,
		"leaf_labels": {0: "1a", 1: "1b"},
		"manuscript": [{"label": "Material", "value": "Palm leaf"}, {"label": "Script", "value": "Grantha"}],
	}
	m = iiif.manifest(
		book,
		BASE,
		provider="P",
		pages=3,
		image_url=lambda leaf: f"https://x/{leaf}.jpg",
		book_url=f"{BASE}/b",
	)
	assert [c["label"] for c in m["items"]] == [{"none": ["1a"]}, {"none": ["1b"]}, {"none": ["3"]}]
	meta = {e["label"]["en"][0]: e["value"] for e in m["metadata"]}
	assert meta["Material"] == {"none": ["Palm leaf"]} and meta["Script"] == {"none": ["Grantha"]}
	assert make()  # a book without them is as before
