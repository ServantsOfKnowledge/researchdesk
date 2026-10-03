"""Preservation copies as OCFL objects (Oxford Common File Layout 1.1). Pure Python, standard library.

OCFL keeps each book as a folder of plain files plus an `inventory.json` that lists every file
with its checksum and every version of the book. Any future system (or a person with a file
browser) can read it without Research Desk, and a changed or missing file is found by checking
the files against the inventory. https://ocfl.io/1.1/spec/

Layout of the storage root (community extension 0003, hash and id n-tuple):

    <root>/0=ocfl_1.1
    <root>/ocfl_layout.json
    <root>/a1b/2c3/d4e/<the book's id, %-encoded>/     one book (an "object"); a1b2c3d4e… is
                                                        the sha256 of its id, so the folder name
                                                        stays readable to a person
        0=ocfl_object_1.1
        inventory.json, inventory.json.sha512
        v1/inventory.json, v1/inventory.json.sha512
        v1/content/<the book's files>
        v2/content/<only files that changed in v2>

A file already in an earlier version is not stored again (the inventory points at it).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import tempfile

SPEC = "1.1"
INVENTORY_TYPE = "https://ocfl.io/1.1/spec/#inventory"
DIGEST = "sha512"
FIXITY = ("md5", "sha256")  # also recorded, to compare with what archive.org publishes (md5)
LAYOUT = {
	"extension": "0003-hash-and-id-n-tuple-storage-layout",
	"description": "Hash and ID N-tuple Storage Layout (sha256, 3 tuples of 3, encoded id)",
}
_PLAIN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
CHUNK = 1 << 20


class OcflError(Exception):
	pass


def _digests(path: str, algorithms=(DIGEST, *FIXITY)) -> dict[str, str]:
	hashes = {a: hashlib.new(a) for a in algorithms}
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(CHUNK), b""):
			for h in hashes.values():
				h.update(block)
	return {a: h.hexdigest() for a, h in hashes.items()}


def _write_json(path: str, data: dict) -> str:
	"""Write JSON and its .sha512 sidecar atomically; returns the digest."""
	body = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
	digest = hashlib.sha512(body).hexdigest()
	for target, content in (
		(path, body),
		(f"{path}.{DIGEST}", f"{digest} {os.path.basename(path)}\n".encode()),
	):
		tmp = f"{target}.tmp"
		with open(tmp, "wb") as f:
			f.write(content)
			f.flush()
			os.fsync(f.fileno())
		os.replace(tmp, target)
	return digest


def init_root(root: str) -> None:
	"""Make `root` an OCFL storage root (does nothing if it already is one)."""
	os.makedirs(root, exist_ok=True)
	marker = os.path.join(root, f"0=ocfl_{SPEC}")
	if not os.path.exists(marker):
		with open(marker, "w") as f:
			f.write(f"ocfl_{SPEC}\n")
	layout = os.path.join(root, "ocfl_layout.json")
	if not os.path.exists(layout):
		with open(layout, "w") as f:
			json.dump(LAYOUT, f, indent=2)


def _encode_id(object_id: str, digest: str) -> str:
	"""Extension 0003: every byte outside [A-Za-z0-9-_] as %xx (lower case); over 100 characters,
	cut to 100 and the digest added."""
	out = "".join(chr(b) if chr(b) in _PLAIN else f"%{b:02x}" for b in object_id.encode("utf-8"))
	return out if len(out) <= 100 else f"{out[:100]}-{digest}"


def object_path(root: str, object_id: str) -> str:
	digest = hashlib.sha256(object_id.encode("utf-8")).hexdigest()
	return os.path.join(root, digest[0:3], digest[3:6], digest[6:9], _encode_id(object_id, digest))


def read_inventory(root: str, object_id: str) -> dict | None:
	path = os.path.join(object_path(root, object_id), "inventory.json")
	if not os.path.exists(path):
		return None
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _safe(logical: str) -> str:
	parts = logical.replace("\\", "/").split("/")
	if not logical or logical.startswith("/") or any(p in ("", ".", "..") for p in parts):
		raise OcflError(f"{logical!r} is not a safe file name inside a book")
	return "/".join(parts)


def write_version(
	root: str,
	object_id: str,
	files: dict[str, str],
	message: str = "",
	user: str = "Research Desk",
	address: str = "",
	move: bool = False,
	created: str | None = None,
) -> dict:
	"""Store `files` ({name inside the book: path on disk}) as the book's newest version.

	Only files whose content is new are copied (or moved, with move=True). Nothing is written when
	the book is unchanged. Returns {version, added_bytes, changed: bool, inventory}."""
	init_root(root)
	files = {_safe(k): v for k, v in files.items()}
	obj = object_path(root, object_id)
	inventory = read_inventory(root, object_id)
	digests = {logical: _digests(path) for logical, path in sorted(files.items())}
	state: dict[str, list[str]] = {}
	for logical, d in digests.items():
		state.setdefault(d[DIGEST], []).append(logical)

	if inventory:
		head = inventory["head"]
		if inventory["versions"][head]["state"] == state:
			return {"version": head, "added_bytes": 0, "changed": False, "inventory": inventory}
		number = int(head[1:]) + 1
	else:
		inventory = {
			"id": object_id,
			"type": INVENTORY_TYPE,
			"digestAlgorithm": DIGEST,
			"contentDirectory": "content",
			"manifest": {},
			"versions": {},
			"fixity": {a: {} for a in FIXITY},
		}
		number = 1
	version = f"v{number}"
	staging = tempfile.mkdtemp(prefix=".ocfl-", dir=root)
	added = 0
	try:
		content = os.path.join(staging, version, "content")
		for logical, d in digests.items():
			digest = d[DIGEST]
			if digest in inventory["manifest"]:
				continue  # the same content is already stored
			target = os.path.join(content, logical)
			os.makedirs(os.path.dirname(target), exist_ok=True)
			(shutil.move if move else shutil.copy2)(files[logical], target)
			added += os.path.getsize(target)
			path = f"{version}/content/{logical}"
			inventory["manifest"][digest] = [path]
			for a in FIXITY:
				inventory["fixity"].setdefault(a, {}).setdefault(d[a], []).append(path)
		inventory["versions"][version] = {
			"created": created or _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
			"message": message,
			"user": {"name": user, **({"address": address} if address else {})},
			"state": state,
		}
		inventory["head"] = version
		_write_json(os.path.join(staging, version, "inventory.json"), inventory)
		os.makedirs(obj, exist_ok=True)
		marker = os.path.join(obj, f"0=ocfl_object_{SPEC}")
		if not os.path.exists(marker):
			with open(marker, "w") as f:
				f.write(f"ocfl_object_{SPEC}\n")
		if os.path.exists(os.path.join(obj, version)):
			raise OcflError(f"{object_id}: {version} already exists (another copy is being written?)")
		os.replace(os.path.join(staging, version), os.path.join(obj, version))
		# the root inventory last: until it names the new version, readers see the old one
		_write_json(os.path.join(obj, "inventory.json"), inventory)
	finally:
		shutil.rmtree(staging, ignore_errors=True)
	return {"version": version, "added_bytes": added, "changed": True, "inventory": inventory}


def verify(root: str, object_id: str) -> dict:
	"""Check a book's files against its inventory: every file there, unchanged, nothing extra.
	Returns {ok, checked, bytes, problems: [text]}."""
	obj = object_path(root, object_id)
	problems: list[str] = []
	inv_path = os.path.join(obj, "inventory.json")
	if not os.path.exists(inv_path):
		return {
			"ok": False,
			"checked": 0,
			"bytes": 0,
			"problems": ["no inventory.json: the book is not stored here"],
		}
	with open(inv_path, "rb") as f:
		body = f.read()
	try:
		with open(f"{inv_path}.{DIGEST}") as f:
			expected = f.read().split()[0]
	except (OSError, IndexError):
		expected = ""
	if hashlib.sha512(body).hexdigest() != expected:
		problems.append("inventory.json does not match its checksum file")
	inventory = json.loads(body)
	checked = size = 0
	listed = set()
	for digest, paths in inventory["manifest"].items():
		for rel in paths:
			listed.add(rel)
			path = os.path.join(obj, rel)
			if not os.path.exists(path):
				problems.append(f"missing: {rel}")
				continue
			checked += 1
			size += os.path.getsize(path)
			if _digests(path, (DIGEST,))[DIGEST] != digest:
				problems.append(f"changed: {rel}")
	for version in inventory["versions"]:
		content = os.path.join(obj, version, "content")
		for dirpath, _dirs, names in os.walk(content):
			for name in names:
				rel = os.path.relpath(os.path.join(dirpath, name), obj).replace(os.sep, "/")
				if rel not in listed:
					problems.append(f"not in the inventory: {rel}")
	return {"ok": not problems, "checked": checked, "bytes": size, "problems": problems}


def head_files(root: str, object_id: str) -> dict[str, str]:
	"""{name inside the book: path on disk} of the newest version (to serve a book from its copy)."""
	inventory = read_inventory(root, object_id)
	if not inventory:
		return {}
	obj = object_path(root, object_id)
	out = {}
	for digest, logicals in inventory["versions"][inventory["head"]]["state"].items():
		for logical in logicals:
			out[logical] = os.path.join(obj, inventory["manifest"][digest][0])
	return out
