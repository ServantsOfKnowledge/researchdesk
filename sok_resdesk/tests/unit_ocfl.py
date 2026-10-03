"""Preservation copies as OCFL objects (core/ocfl.py). Pure Python, on real files in a temp folder."""

import hashlib
import json
import os

import pytest

from sok_resdesk.core import ocfl


def _files(tmp_path, **contents):
	out = {}
	for name, text in contents.items():
		path = tmp_path / "src" / name.replace("__", "/")
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_bytes(text.encode())
		out[name.replace("__", "/")] = str(path)
	return out


def test_a_book_is_stored_as_a_valid_ocfl_object(tmp_path):
	root = str(tmp_path / "store")
	files = _files(tmp_path, **{"book.pdf": "PDF", "book_meta.xml": "<meta/>", "text__p1.txt": "ಕನಕ"})
	r = ocfl.write_version(
		root, "kanakadasa01", files, message="from archive.org", created="2026-10-05T00:00:00+00:00"
	)
	assert (
		r["changed"] and r["version"] == "v1" and r["added_bytes"] == len("PDF<meta/>") + len("ಕನಕ".encode())
	)
	assert os.path.exists(os.path.join(root, "0=ocfl_1.1"))
	obj = ocfl.object_path(root, "kanakadasa01")
	digest = hashlib.sha256(b"kanakadasa01").hexdigest()
	assert obj.endswith(os.path.join(digest[:3], digest[3:6], digest[6:9], "kanakadasa01"))
	assert ocfl.object_path(root, "a.b/c").endswith("a%2eb%2fc")  # extension 0003 encoding
	long = "x" * 120
	assert (
		os.path.basename(ocfl.object_path(root, long))
		== "x" * 100 + "-" + hashlib.sha256(long.encode()).hexdigest()
	)
	inv = json.load(open(os.path.join(obj, "inventory.json")))
	assert inv["head"] == "v1" and inv["id"] == "kanakadasa01" and inv["digestAlgorithm"] == "sha512"
	assert sorted(p for ps in inv["versions"]["v1"]["state"].values() for p in ps) == [
		"book.pdf",
		"book_meta.xml",
		"text/p1.txt",
	]
	assert hashlib.md5(b"PDF").hexdigest() in inv["fixity"]["md5"]  # comparable with archive.org's md5
	assert os.path.exists(os.path.join(obj, "v1", "inventory.json.sha512"))
	assert ocfl.verify(root, "kanakadasa01") == {
		"ok": True,
		"checked": 3,
		"bytes": r["added_bytes"],
		"problems": [],
	}
	assert open(ocfl.head_files(root, "kanakadasa01")["text/p1.txt"]).read() == "ಕನಕ"


def test_unchanged_books_are_not_written_again_and_changes_store_only_what_changed(tmp_path):
	root = str(tmp_path / "store")
	ocfl.write_version(root, "b", _files(tmp_path, **{"a.txt": "one", "b.txt": "two"}))
	again = ocfl.write_version(root, "b", _files(tmp_path, **{"a.txt": "one", "b.txt": "two"}))
	assert not again["changed"] and again["version"] == "v1"
	v2 = ocfl.write_version(root, "b", _files(tmp_path, **{"a.txt": "one", "b.txt": "TWO"}))
	assert v2["version"] == "v2" and v2["added_bytes"] == 3
	obj = ocfl.object_path(root, "b")
	assert os.listdir(os.path.join(obj, "v2", "content")) == ["b.txt"]  # a.txt points back at v1
	assert open(ocfl.head_files(root, "b")["b.txt"]).read() == "TWO"
	assert open(ocfl.head_files(root, "b")["a.txt"]).read() == "one"
	assert ocfl.verify(root, "b")["ok"]


def test_verify_finds_changed_missing_and_extra_files(tmp_path):
	root = str(tmp_path / "store")
	ocfl.write_version(root, "b", _files(tmp_path, **{"a.txt": "one", "b.txt": "two", "c.txt": "three"}))
	obj = ocfl.object_path(root, "b")
	open(os.path.join(obj, "v1", "content", "a.txt"), "w").write("0ne")  # bit rot
	os.remove(os.path.join(obj, "v1", "content", "b.txt"))
	open(os.path.join(obj, "v1", "content", "stray.txt"), "w").write("?")
	r = ocfl.verify(root, "b")
	assert not r["ok"]
	assert set(r["problems"]) == {
		"changed: v1/content/a.txt",
		"missing: v1/content/b.txt",
		"not in the inventory: v1/content/stray.txt",
	}
	open(os.path.join(obj, "inventory.json"), "a").write(" ")
	assert "inventory.json does not match its checksum file" in ocfl.verify(root, "b")["problems"]
	assert not ocfl.verify(root, "never-stored")["ok"]


def test_moving_files_in_and_unsafe_names(tmp_path):
	root = str(tmp_path / "store")
	files = _files(tmp_path, **{"a.txt": "one"})
	ocfl.write_version(root, "m", files, move=True)
	assert not os.path.exists(files["a.txt"]) and ocfl.verify(root, "m")["ok"]
	for bad in ("../x", "/etc/passwd", "a//b", "a/./b"):
		with pytest.raises(ocfl.OcflError):
			ocfl.write_version(root, "m", {bad: str(tmp_path)})
