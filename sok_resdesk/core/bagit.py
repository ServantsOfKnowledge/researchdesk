"""BagIt (RFC 8493) bags of preserved books, for handing them to another archive.

A bag is a folder that carries its own checksums: `bagit.txt`, `bag-info.txt` (who, what,
when), `data/` with the book's files, `manifest-sha512.txt` listing every file under data/, and
`tagmanifest-sha512.txt` listing the others. Any BagIt tool (the Library of Congress's
`bagit-python`, Archivematica, DSpace) validates and unpacks it.

Bags are written into a zip file, one bag per book (a folder per bag), so a whole collection
travels as one file. Pure Python, standard library.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import zipfile

VERSION = "1.0"
CHUNK = 1 << 20


def _sha512_file(path: str) -> tuple[str, int]:
	h, size = hashlib.sha512(), 0
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(CHUNK), b""):
			h.update(block)
			size += len(block)
	return h.hexdigest(), size


def _safe(name: str) -> str:
	parts = name.replace("\\", "/").split("/")
	if not name or name.startswith("/") or any(p in ("", ".", "..") for p in parts):
		raise ValueError(f"{name!r} is not a safe file name inside a bag")
	return "/".join(parts)


def _encode(path: str) -> str:
	"""RFC 8493 §2.1.3: CR, LF and % in manifest paths are percent-encoded."""
	return path.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")


def add_bag(z: zipfile.ZipFile, bag_name: str, files: dict[str, str], info: dict[str, str]) -> dict:
	"""Write one bag into the open zip `z` under `bag_name/`. `files` = {name in the book: path on
	disk}; `info` = bag-info.txt fields (Source-Organization, External-Identifier, …).
	Returns {files, bytes}."""
	bag_name = _safe(bag_name)
	manifest, total = [], 0
	for name, path in sorted(files.items()):
		rel = f"data/{_safe(name)}"
		digest, size = _sha512_file(path)
		z.write(path, f"{bag_name}/{rel}")
		manifest.append(f"{digest}  {_encode(rel)}")
		total += size
	tags = {
		"bagit.txt": f"BagIt-Version: {VERSION}\nTag-File-Character-Encoding: UTF-8\n",
		"manifest-sha512.txt": "\n".join(manifest) + "\n",
	}
	fields = {
		"Bagging-Date": _dt.date.today().isoformat(),
		"Payload-Oxum": f"{total}.{len(files)}",
		**{k: v for k, v in info.items() if v},
	}
	tags["bag-info.txt"] = "".join(f"{k}: {' '.join(str(v).split())}\n" for k, v in fields.items())
	for name, body in tags.items():
		z.writestr(f"{bag_name}/{name}", body)
	tag_manifest = "".join(
		f"{hashlib.sha512(tags[n].encode()).hexdigest()}  {n}\n"
		for n in ("bag-info.txt", "bagit.txt", "manifest-sha512.txt")
	)
	z.writestr(f"{bag_name}/tagmanifest-sha512.txt", tag_manifest)
	return {"files": len(files), "bytes": total}


def write_bags(out_path: str, books: list[tuple[str, dict[str, str], dict[str, str]]]) -> dict:
	"""A zip of bags: books = [(bag name, files, info)]. Written to `out_path` via a temporary file.
	Returns {bags, files, bytes}."""
	os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
	tmp = f"{out_path}.tmp"
	totals = {"bags": 0, "files": 0, "bytes": 0}
	# stored, not deflated: scans and PDFs are compressed already, and a bag should open fast
	with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
		for bag_name, files, info in books:
			r = add_bag(z, bag_name, files, info)
			totals["bags"] += 1
			totals["files"] += r["files"]
			totals["bytes"] += r["bytes"]
	os.replace(tmp, out_path)
	return totals


def validate(zip_path: str, bag_name: str) -> list[str]:
	"""Problems with one bag inside a zip ([] = valid): every manifest line's file present with that
	checksum, nothing extra under data/, the tag manifest right."""
	problems = []
	with zipfile.ZipFile(zip_path) as z:
		names = set(z.namelist())
		prefix = f"{bag_name}/"

		def read(n):
			return z.read(prefix + n) if prefix + n in names else None

		if read("bagit.txt") is None:
			return ["no bagit.txt"]
		listed = set()
		for line in (read("manifest-sha512.txt") or b"").decode().splitlines():
			if not line.strip():
				continue
			digest, rel = line.split(None, 1)
			rel = rel.replace("%0D", "\r").replace("%0A", "\n").replace("%25", "%")
			listed.add(rel)
			if prefix + rel not in names:
				problems.append(f"missing: {rel}")
				continue
			h = hashlib.sha512()
			with z.open(prefix + rel) as f:
				for block in iter(lambda f=f: f.read(CHUNK), b""):
					h.update(block)
			if h.hexdigest() != digest:
				problems.append(f"changed: {rel}")
		for n in names:
			if n.startswith(prefix + "data/") and n[len(prefix) :] not in listed:
				problems.append(f"not in the manifest: {n[len(prefix) :]}")
		for line in (read("tagmanifest-sha512.txt") or b"").decode().splitlines():
			if line.strip():
				digest, rel = line.split(None, 1)
				body = read(rel)
				if body is None or hashlib.sha512(body).hexdigest() != digest:
					problems.append(f"tag file changed: {rel}")
	return problems
