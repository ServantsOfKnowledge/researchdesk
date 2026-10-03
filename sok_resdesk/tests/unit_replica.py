"""The second copy (core/replica.py), the object copy and repair (core/ocfl.py) and BagIt bags
(core/bagit.py)."""

import base64
import hashlib
import io
import os
import zipfile

import pytest

from sok_resdesk.core import bagit, ocfl
from sok_resdesk.core.replica import FolderReplica, S3Replica

ID = "kanakadasa1950"


def _book(tmp_path, root, text=b"page text", pdf=b"%PDF-1.4 scan"):
	src = tmp_path / "src"
	src.mkdir(exist_ok=True)
	(src / "book.pdf").write_bytes(pdf)
	(src / "text.txt").write_bytes(text)
	return ocfl.write_version(
		str(root), ID, {"book.pdf": str(src / "book.pdf"), "text.txt": str(src / "text.txt")}
	)


def _break(root, name="book.pdf", how="change"):
	path = os.path.join(ocfl.object_path(str(root), ID), "v1", "content", name)
	if how == "change":
		with open(path, "ab") as f:
			f.write(b"rot")
	else:
		os.remove(path)


def test_copy_and_install_check_before_replacing(tmp_path):
	a, b = tmp_path / "a", tmp_path / "b"
	_book(tmp_path, a)
	assert ocfl.copy_object(str(a), str(b), ID)["ok"]
	assert ocfl.verify(str(b), ID)["ok"]
	# a damaged source is refused, and the good copy at the destination stays as it was
	_break(a)
	with pytest.raises(ocfl.OcflError):
		ocfl.copy_object(str(a), str(b), ID)
	assert ocfl.verify(str(b), ID)["ok"]
	assert not [n for n in os.listdir(b) if n.startswith(".")]  # no staging folders left behind
	assert ocfl.object_files(str(b), ID)[-2:] == ["inventory.json", "inventory.json.sha512"]


def test_folder_replica_push_check_repair_restore(tmp_path):
	first, second = tmp_path / "first", tmp_path / "second"
	scan = b"%PDF-1.4 " + os.urandom(200_000)
	_book(tmp_path, first, pdf=scan)
	rep = FolderReplica(str(second))
	first_push = rep.push(str(first), ID)["bytes"]
	assert first_push > 0 and rep.push(str(first), ID)["bytes"] == 0
	assert rep.verify(ID)["ok"] and not rep.verify(ID)["light"]
	# a second version: only what changed is copied
	_book(tmp_path, first, text=b"corrected text", pdf=scan)
	sent = rep.push(str(first), ID)["bytes"]
	assert first_push > 200_000 and 0 < sent < 20_000 and rep.verify(ID)["ok"]  # the scan isn't sent again
	# the second copy rots → rebuilt from the first
	path = os.path.join(ocfl.object_path(str(second), ID), "v1", "content", "book.pdf")
	with open(path, "ab") as f:
		f.write(b"x")
	assert not rep.verify(ID)["ok"]
	assert rep.repair(str(first), ID)["ok"]
	# the first copy loses a file → rebuilt from the second
	_break(first, how="remove")
	assert not ocfl.verify(str(first), ID)["ok"]
	assert rep.restore(str(first), ID)["ok"]
	assert ocfl.verify(str(first), ID)["ok"]


class FakeS3:
	"""What S3 does that matters here: keys, sizes, ETag = MD5 of a single upload, Content-MD5
	checked on arrival, listing in pages."""

	def __init__(self, page_size=3):
		self.objects, self.page_size = {}, page_size

	def put_object(self, Bucket, Key, Body, ContentMD5=None):
		data = Body.read()
		md5 = hashlib.md5(data)
		if ContentMD5 and base64.b64encode(md5.digest()).decode() != ContentMD5:
			raise ValueError("BadDigest")
		self.objects[Key] = (data, md5.hexdigest())

	def get_object(self, Bucket, Key):
		return {"Body": io.BytesIO(self.objects[Key][0])}

	def delete_object(self, Bucket, Key):
		self.objects.pop(Key, None)

	def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
		keys = sorted(k for k in self.objects if k.startswith(Prefix))
		start = int(ContinuationToken or 0)
		page = keys[start : start + self.page_size]
		more = start + self.page_size < len(keys)
		out = {
			"Contents": [
				{"Key": k, "Size": len(self.objects[k][0]), "ETag": f'"{self.objects[k][1]}"'} for k in page
			],
			"IsTruncated": more,
		}
		if more:
			out["NextContinuationToken"] = str(start + self.page_size)
		return out


def test_s3_replica_push_check_repair_restore(tmp_path):
	first = tmp_path / "first"
	_book(tmp_path, first)
	s3 = FakeS3()
	rep = S3Replica(s3, "library-copies", "sok/")
	rep.push(str(first), ID)
	key = f"sok/{ocfl.object_rel(ID)}/inventory.json"
	assert key in s3.objects
	check = rep.verify(ID)
	assert check["ok"] and check["light"] and check["checked"] == 2
	# nothing new → nothing sent but the inventories
	assert rep.push(str(first), ID)["bytes"] < 4000
	# rot on the service: an object whose ETag no longer matches the inventory's MD5
	pdf = f"sok/{ocfl.object_rel(ID)}/v1/content/book.pdf"
	s3.objects[pdf] = (b"rotten", hashlib.md5(b"rotten").hexdigest())
	s3.objects[f"sok/{ocfl.object_rel(ID)}/v1/content/stray.bin"] = (b"x", hashlib.md5(b"x").hexdigest())
	problems = rep.verify(ID)["problems"]
	assert any(p.startswith("changed:") for p in problems) and any(
		"not in the inventory" in p for p in problems
	)
	assert rep.repair(str(first), ID)["ok"]
	# the first copy is lost entirely → rebuilt from the service
	import shutil

	shutil.rmtree(ocfl.object_path(str(first), ID))
	assert rep.restore(str(first), ID)["ok"]
	assert ocfl.verify(str(first), ID)["ok"]
	assert S3Replica(FakeS3(), "b").verify(ID)["problems"][0].startswith("no inventory.json")


def test_bagit_bags_validate_and_catch_damage(tmp_path):
	first = tmp_path / "first"
	_book(tmp_path, first)
	files = ocfl.head_files(str(first), ID)
	out = tmp_path / "exports" / "bags.zip"
	totals = bagit.write_bags(
		str(out), [(ID, files, {"Source-Organization": "Servants of Knowledge", "External-Identifier": ID})]
	)
	assert totals == {"bags": 1, "files": 2, "bytes": len(b"%PDF-1.4 scan") + len(b"page text")}
	assert bagit.validate(str(out), ID) == []
	with zipfile.ZipFile(out) as z:
		info = z.read(f"{ID}/bag-info.txt").decode()
	assert "Payload-Oxum: 22.2" in info and "Source-Organization: Servants of Knowledge" in info
	# a damaged bag is caught
	bad = tmp_path / "bad.zip"
	with zipfile.ZipFile(out) as z, zipfile.ZipFile(bad, "w") as w:
		for n in z.namelist():
			w.writestr(n, b"tampered" if n.endswith("book.pdf") else z.read(n))
	assert bagit.validate(str(bad), ID) == ["changed: data/book.pdf"]
	with pytest.raises(ValueError):
		bagit.write_bags(str(tmp_path / "x.zip"), [("../evil", files, {})])
