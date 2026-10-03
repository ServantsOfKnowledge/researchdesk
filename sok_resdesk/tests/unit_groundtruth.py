"""Ground-truth sets (core/groundtruth.py): pairs, zone splitting, the zip, licences."""

import csv
import io
import json
import zipfile

import pytest

from sok_resdesk.core import groundtruth as gt
from sok_resdesk.core import zones as zn


def _jpeg(w=200, h=300):
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (w, h), "white").save(buf, format="JPEG")
	return buf.getvalue()


PAGE = {
	"item": "kanakadasa1950",
	"title": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು",
	"leaf": 7,
	"page_label": "5",
	"text": "ಮೊದಲನೆಯ ಭಾಗ\nಹರಿದಾಸ\n\nಎರಡನೆಯ ಅಧ್ಯಾಯ",
	"zones": [zn.zone(2, 2, 48, 96), zn.zone(50, 2, 48, 96)],
	"language": "kan",
	"status": "Validated",
	"source": "Proofreading",
	"quality": 92,
	"proofread_by": "",
	"validated_by": "",
	"page_url": "https://lib.example/library/item/kanakadasa1950?page=7&view=text",
}


def test_zone_texts_pair_up_only_when_the_paragraphs_match():
	pairs = gt.zone_pairs(PAGE["text"], PAGE["zones"])
	assert [t for _, t in pairs] == ["ಮೊದಲನೆಯ ಭಾಗ\nಹರಿದಾಸ", "ಎರಡನೆಯ ಅಧ್ಯಾಯ"]
	assert gt.zone_pairs("one paragraph only", PAGE["zones"]) == []  # joined by the proofreader
	assert gt.zone_pairs(PAGE["text"], [zn.zone(0, 0, 100, 100)]) == []  # one zone: the page itself
	skip = [*PAGE["zones"], zn.zone(80, 90, 10, 5, "skip")]
	assert len(gt.zone_pairs(PAGE["text"], skip)) == 2  # skipped parts carry no text
	assert gt.zone_pairs(PAGE["text"], "not json") == []


def test_licences():
	assert gt.licence("") is None and gt.licence("GPL") is None
	assert gt.licence("CC-BY-4.0")["url"] == "https://creativecommons.org/licenses/by/4.0/"


def _build(tmp_path, licence="CC0-1.0", pages=None, with_zones=True):
	path = tmp_path / "gt.zip"
	log = []

	def image_of(item, leaf):
		if leaf == 99:
			raise RuntimeError("archive.org did not send it")
		return _jpeg()

	meta = {
		"name": "GT-00001",
		"title": "Kannada test set",
		"organisation": "SOK",
		"url": "https://lib.example",
		"licence": licence,
		"attribution": "SOK proofreaders",
		"created": "2026-10-08",
	}
	counts = gt.write(str(path), pages or [PAGE], image_of, meta, with_zones, log.append)
	return path, counts, log


def test_a_set_holds_pages_zones_manifest_and_licence(tmp_path):
	path, counts, _ = _build(tmp_path)
	assert counts == {"pages": 1, "zones": 2, "books": 1, "skipped": 0, "languages": {"kan": 1}}
	with zipfile.ZipFile(path) as z:
		names = set(z.namelist())
		assert {
			"pages/kanakadasa1950/0007.jpg",
			"pages/kanakadasa1950/0007.gt.txt",
			"zones/kanakadasa1950/0007-01.png",
			"zones/kanakadasa1950/0007-02.gt.txt",
			"manifest.csv",
			"manifest.jsonl",
			"datapackage.json",
			"README.md",
			"LICENSE.txt",
		} <= names
		assert z.read("pages/kanakadasa1950/0007.gt.txt").decode() == PAGE["text"] + "\n"
		assert z.read("zones/kanakadasa1950/0007-02.gt.txt").decode() == "ಎರಡನೆಯ ಅಧ್ಯಾಯ\n"
		rows = list(csv.DictReader(io.StringIO(z.read("manifest.csv").decode())))
		assert [r["kind"] for r in rows] == ["page", "zone", "zone"]
		assert rows[0]["lines"] == "3" and rows[0]["width"] == "200" and rows[1]["width"] == "96"
		import hashlib

		assert rows[0]["text_sha256"] == hashlib.sha256(z.read(rows[0]["text"])).hexdigest()
		pkg = json.loads(z.read("datapackage.json"))
		assert pkg["licenses"][0]["name"] == "CC0-1.0" and pkg["resources"][0]["path"] == "manifest.csv"
		assert (
			"CC0 1.0" in z.read("README.md").decode() and "SOK proofreaders" in z.read("LICENSE.txt").decode()
		)


def test_without_a_licence_the_set_says_it_is_not_for_sharing(tmp_path):
	path, _, _ = _build(tmp_path, licence=None)
	with zipfile.ZipFile(path) as z:
		assert "not for redistribution" in z.read("LICENSE.txt").decode()
		assert "licenses" not in json.loads(z.read("datapackage.json"))


def test_pages_without_images_are_left_out_and_logged(tmp_path):
	missing = {**PAGE, "leaf": 99}
	_, counts, log = _build(tmp_path, pages=[PAGE, missing], with_zones=False)
	assert counts["pages"] == 1 and counts["zones"] == 0 and counts["skipped"] == 1
	assert "page 99" in log[0]


@pytest.mark.parametrize("name", ["../etc", "a/b", ""])
def test_book_folders_stay_inside_the_set(name):
	assert "/" not in gt._safe(name) and not gt._safe(name).startswith(".")
