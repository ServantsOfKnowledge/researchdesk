"""0.55: a folder of photographs as a book (no Frappe)."""

import io
import json
import os

from PIL import Image

from sok_resdesk.core import leafimages as li
from sok_resdesk.core.folder import FolderStore


def photo(path, size=(2400, 300), colour=(180, 140, 80), fmt="JPEG"):
	Image.new("RGB", size, colour).save(path, fmt)


def test_leaves_are_in_natural_order_and_previews_are_left_out():
	files = ["leaf10.jpg", "leaf2.jpg", "Leaf1.JPG", "thumb_1.jpg", ".hidden.jpg", "notes.txt", "scan.TIF"]
	assert li.leaf_names(files) == ["Leaf1.JPG", "leaf2.jpg", "leaf10.jpg", "scan.TIF"]


def test_a_folder_of_images_is_a_bundle_unless_it_is_something_else():
	assert li.is_bundle(["1.jpg", "2.jpg"])
	assert not li.is_bundle(["1.jpg"])  # one photograph is not a book…
	assert li.is_bundle(["1.jpg", "bundle.json"])  # …unless it says so
	assert not li.is_bundle(["1.jpg", "2.jpg", "book.pdf"])
	assert not li.is_bundle(["1.jpg", "2.jpg", "x_meta.xml"])  # an archive.org item folder
	assert li.bundle_id("palm/Rama yana 3") == "img-palm-Rama-yana-3"


def test_the_sidecar_gives_details_and_a_bundle_is_a_manuscript_unless_told_otherwise():
	raw = json.dumps(
		{"title": "Ramayana", "creator": ["Valmiki"], "manuscript": {"script": "Grantha", "leaves": 40}}
	).encode()
	meta = li.sidecar_meta(raw, "bundle_3")
	assert meta["title"] == "Ramayana" and meta["creator"] == ["Valmiki"] and "manuscript" not in meta
	assert li.sidecar_meta(None, "Palm_leaf_bundle_3")["title"] == "Palm leaf bundle 3"
	assert li.sidecar_meta(b"not json", "x")["title"] == "x"
	opts = li.sidecar_options(raw)
	assert (opts["item_type"], opts["ocr"], opts["manuscript"]) == (
		"Manuscript",
		False,
		{"ms_script": "Grantha", "ms_leaves": 40},
	)
	printed = li.sidecar_options(json.dumps({"item_type": "Book"}).encode())
	assert (printed["item_type"], printed["ocr"]) == ("Book", True)  # printed leaves are read with OCR


def test_a_photograph_is_made_upright_and_not_too_large(tmp_path):
	big = tmp_path / "big.png"
	photo(str(big), (9000, 400), fmt="PNG")
	with li.open_image(str(big)) as im:
		assert im.size == (li.MAX_SIDE, round(400 * li.MAX_SIDE / 9000))
	data = li.to_jpeg(li.open_image(str(big)))
	assert data[:2] == b"\xff\xd8"
	small = li.resize_to_width(data, 800)
	with Image.open(io.BytesIO(small)) as im:
		assert im.width == 800
	assert li.resize_to_width(data, 99999) == data  # never made larger


def test_the_folder_store_finds_a_bundle_and_its_leaves(tmp_path):
	b = tmp_path / "palm" / "Bundle 1"
	b.mkdir(parents=True)
	for n in (2, 10, 1):
		photo(str(b / f"leaf{n}.jpg"))
	(b / "bundle.json").write_text(json.dumps({"title": "A bundle"}))
	loose = tmp_path / "other"
	loose.mkdir()
	photo(str(loose / "one.jpg"))
	store = FolderStore(str(tmp_path))
	items = dict(store.iter_items())
	assert items == {"img-palm-Bundle-1": "palm/Bundle 1"}  # one photograph alone is not a book
	loc = items["img-palm-Bundle-1"]
	assert store.is_bundle(loc) and store.leaves(loc) == ["leaf1.jpg", "leaf2.jpg", "leaf10.jpg"]
	data = store.load_item("img-palm-Bundle-1", loc)
	assert data["metadata"]["title"] == "A bundle" and data["metadata"]["imagecount"] == 3
	before = store.signature(loc, "x")
	photo(str(b / "leaf2.jpg"), (2400, 301))
	later = os.stat(b / "leaf2.jpg").st_mtime + 10
	os.utime(b / "leaf2.jpg", (later, later))  # (a second may not have passed)
	assert store.signature(loc, "x") != before
