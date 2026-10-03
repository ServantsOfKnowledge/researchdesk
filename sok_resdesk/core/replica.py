"""The second copy of the preservation copies: another folder, or S3-compatible object storage.

Both hold the same OCFL objects as the first copy (core/ocfl.py), at the same paths, so either
can be read on its own by any OCFL tool, and either can rebuild the other.

* **FolderReplica**: a folder on another disk, a NAS, or a partner's storage mounted on this
  server. Checked like the first copy: every file's sha512 against the inventory.
* **S3Replica**: a bucket on any S3-compatible service (AWS, Wasabi, Backblaze B2, MinIO, a
  partner's Ceph…). Files are uploaded whole with their MD5, which the service checks on arrival
  and keeps as the file's ETag; a check compares every ETag with the MD5 the inventory records,
  without downloading the files.

Pure Python: the S3 client is passed in (boto3's interface: list_objects_v2, put_object,
get_object, delete_object), so the logic is tested without a network.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile

from sok_resdesk.core import ocfl

CHUNK = 1 << 20


def _md5(path: str) -> str:
	h = hashlib.md5()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(CHUNK), b""):
			h.update(block)
	return h.hexdigest()


def _same(a: str, b: str) -> bool:
	with open(a, "rb") as fa, open(b, "rb") as fb:
		return fa.read() == fb.read()


def _is_content(rel: str) -> bool:
	parts = rel.split("/")
	return len(parts) > 2 and parts[1] == "content"


def _md5_by_path(inventory: dict) -> dict[str, str]:
	out = {}
	for md5, paths in (inventory.get("fixity") or {}).get("md5", {}).items():
		for p in paths:
			out[p] = md5
	return out


class Replica:
	kind = "base"

	def describe(self) -> str:
		raise NotImplementedError

	def push(self, root: str, object_id: str) -> dict:
		"""Bring the second copy up to the first (only what is new). Returns {files, bytes}."""
		raise NotImplementedError

	def verify(self, object_id: str) -> dict:
		"""{ok, checked, bytes, problems, light}: light = checked by the service's checksums."""
		raise NotImplementedError

	def restore(self, root: str, object_id: str) -> dict:
		"""Rebuild the first copy from this one. Returns ocfl.verify() of the rebuilt object."""
		raise NotImplementedError

	def repair(self, root: str, object_id: str) -> dict:
		"""Rebuild this copy from the first one. Returns this copy's verify()."""
		raise NotImplementedError


class FolderReplica(Replica):
	kind = "Folder"

	def __init__(self, root: str):
		self.root = root

	def describe(self) -> str:
		return self.root

	def push(self, root: str, object_id: str) -> dict:
		ocfl.init_root(self.root)
		src = ocfl.object_path(root, object_id)
		dst = ocfl.object_path(self.root, object_id)
		files = copied = 0
		for rel in ocfl.object_files(root, object_id):
			source, target = os.path.join(src, rel), os.path.join(dst, rel)
			files += 1
			# a version's content never changes once written: already there, same size → skip;
			# inventories and markers (a few kilobytes) are compared byte for byte
			if os.path.exists(target) and os.path.getsize(target) == os.path.getsize(source):
				if _is_content(rel) or _same(source, target):
					continue
			os.makedirs(os.path.dirname(target), exist_ok=True)
			tmp = f"{target}.tmp"
			shutil.copy2(source, tmp)
			os.replace(tmp, target)
			copied += os.path.getsize(target)
		return {"files": files, "bytes": copied}

	def verify(self, object_id: str) -> dict:
		return {**ocfl.verify(self.root, object_id), "light": False}

	def restore(self, root: str, object_id: str) -> dict:
		return ocfl.copy_object(self.root, root, object_id)

	def repair(self, root: str, object_id: str) -> dict:
		ocfl.copy_object(root, self.root, object_id)
		return self.verify(object_id)


class S3Replica(Replica):
	kind = "S3"

	def __init__(self, client, bucket: str, prefix: str = ""):
		self.client, self.bucket, self.prefix = client, bucket, prefix.strip("/")

	def describe(self) -> str:
		return f"s3://{self.bucket}/{self.prefix}".rstrip("/")

	def _base(self, object_id: str) -> str:
		rel = ocfl.object_rel(object_id)
		return f"{self.prefix}/{rel}" if self.prefix else rel

	def _listing(self, object_id: str) -> dict[str, dict]:
		"""{path inside the object: {size, etag}} as the service has it."""
		base = self._base(object_id) + "/"
		out, token = {}, None
		while True:
			args = {"Bucket": self.bucket, "Prefix": base}
			if token:
				args["ContinuationToken"] = token
			page = self.client.list_objects_v2(**args)
			for o in page.get("Contents") or []:
				out[o["Key"][len(base) :]] = {
					"size": o.get("Size", 0),
					"etag": (o.get("ETag") or "").strip('"'),
				}
			if not page.get("IsTruncated"):
				return out
			token = page.get("NextContinuationToken")

	def _put(self, key: str, path: str) -> None:
		md5 = hashlib.md5()
		with open(path, "rb") as f:
			for block in iter(lambda: f.read(CHUNK), b""):
				md5.update(block)
		with open(path, "rb") as f:
			# one request per file with its MD5: the service refuses a damaged upload, and the
			# ETag it keeps is that MD5, which later checks compare against the inventory
			self.client.put_object(
				Bucket=self.bucket, Key=key, Body=f, ContentMD5=base64.b64encode(md5.digest()).decode()
			)

	def _get(self, key: str) -> bytes:
		return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

	def push(self, root: str, object_id: str, prune: bool = False) -> dict:
		inventory = ocfl.read_inventory(root, object_id)
		if not inventory:
			raise ocfl.OcflError(f"{object_id}: not stored in {root}")
		md5s = _md5_by_path(inventory)
		have = self._listing(object_id)
		src, base = ocfl.object_path(root, object_id), self._base(object_id)
		local = ocfl.object_files(root, object_id)
		files = sent = 0
		for rel in local:
			path = os.path.join(src, rel)
			files += 1
			if _is_content(rel) and rel in have:
				want = md5s.get(rel) or _md5(path)
				if have[rel]["etag"] == want:
					continue
			self._put(f"{base}/{rel}", path)
			sent += os.path.getsize(path)
		if prune:
			for rel in set(have) - set(local):
				self.client.delete_object(Bucket=self.bucket, Key=f"{base}/{rel}")
		return {"files": files, "bytes": sent}

	def verify(self, object_id: str) -> dict:
		have = self._listing(object_id)
		result = {"ok": False, "checked": 0, "bytes": 0, "problems": [], "light": True}
		if "inventory.json" not in have:
			result["problems"].append("no inventory.json: the book is not stored here")
			return result
		base = self._base(object_id)
		body = self._get(f"{base}/inventory.json")
		try:
			expected = self._get(f"{base}/inventory.json.{ocfl.DIGEST}").decode().split()[0]
		except Exception:
			expected = ""
		problems = result["problems"]
		if hashlib.sha512(body).hexdigest() != expected:
			problems.append("inventory.json does not match its checksum file")
		inventory = json.loads(body)
		md5s = _md5_by_path(inventory)
		listed = set()
		for paths in inventory["manifest"].values():
			for rel in paths:
				listed.add(rel)
				got = have.get(rel)
				if not got:
					problems.append(f"missing: {rel}")
					continue
				result["checked"] += 1
				result["bytes"] += got["size"]
				if "-" in got["etag"]:
					problems.append(f"can't be checked (uploaded in parts by another tool): {rel}")
				elif md5s.get(rel) and got["etag"] != md5s[rel]:
					problems.append(f"changed: {rel}")
		for rel in have:
			if _is_content(rel) and rel not in listed:
				problems.append(f"not in the inventory: {rel}")
		result["ok"] = not problems
		return result

	def restore(self, root: str, object_id: str) -> dict:
		have = self._listing(object_id)
		if "inventory.json" not in have:
			raise ocfl.OcflError(f"{object_id}: not stored in {self.describe()}")
		ocfl.init_root(root)
		staging = tempfile.mkdtemp(prefix=".restore-", dir=root)
		base = self._base(object_id)
		try:
			staged = os.path.join(staging, "object")
			for rel in have:
				target = os.path.join(staged, rel)
				os.makedirs(os.path.dirname(target), exist_ok=True)
				with open(target, "wb") as f:
					stream = self.client.get_object(Bucket=self.bucket, Key=f"{base}/{rel}")["Body"]
					shutil.copyfileobj(stream, f, CHUNK)
			return ocfl.install_object(root, object_id, staged)
		finally:
			shutil.rmtree(staging, ignore_errors=True)

	def repair(self, root: str, object_id: str) -> dict:
		self.push(root, object_id, prune=True)
		return self.verify(object_id)
