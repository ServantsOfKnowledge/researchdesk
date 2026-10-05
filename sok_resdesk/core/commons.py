"""Putting a photograph on Wikimedia Commons: the file name, the licence, the description page and
the structured data (depicts). Pure Python (no Frappe), so it is unit-tested directly.

Commons takes only freely licensed (or public-domain) files, and only from someone entitled to
publish them, so the licence must be one of the free ones below and the sender confirms that
the photograph is theirs (or that its owner agreed) before anything leaves.
"""

from __future__ import annotations

import hashlib
import json
import re

SITE = "commons.wikimedia.org"
# 100 MB: the plain upload Commons accepts in one request (larger files need chunked upload)
MAX_BYTES = 100 * 1024 * 1024
MAX_NAME_BYTES = 240

# (licence URL fragment, template on Commons, label) — free licences only
LICENCES = [
	("publicdomain/zero/1.0", "{{Cc-zero}}", "CC0 1.0"),
	("licenses/by-sa/4.0", "{{Cc-by-sa-4.0}}", "CC BY-SA 4.0"),
	("licenses/by-sa/3.0", "{{Cc-by-sa-3.0}}", "CC BY-SA 3.0"),
	("licenses/by/4.0", "{{Cc-by-4.0}}", "CC BY 4.0"),
	("licenses/by/3.0", "{{Cc-by-3.0}}", "CC BY 3.0"),
	("publicdomain/mark/1.0", "{{PD-old}}", "Public domain"),
]
TYPES = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "tif": "tif", "tiff": "tif", "webp": "webp"}
_BAD = re.compile(r"[#<>\[\]|{}:/\\\x00-\x1f]")


def licence_for(url: str) -> tuple[str, str] | None:
	"""(Commons template, label) for a licence URL that Commons accepts, else None."""
	u = (url or "").lower().replace("http://", "https://")
	for fragment, template, label in LICENCES:
		if fragment in u:
			return template, label
	return None


def licence_problem(url: str) -> str:
	"""'' when Commons can take the photograph under its licence, else why not."""
	if not (url or "").strip():
		return "The photograph has no licence: set a Licence URL (Rights section) first."
	if licence_for(url):
		return ""
	return (
		"Commons takes only free licences (CC0, CC BY, CC BY-SA, public domain). "
		"The licence this photograph carries is not one of them."
	)


def sha1_of(path: str) -> str:
	h = hashlib.sha1()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(1 << 20), b""):
			h.update(block)
	return h.hexdigest()


def extension(name: str) -> str:
	return TYPES.get(name.rsplit(".", 1)[-1].lower(), "") if "." in name else ""


def file_name(title: str, ext: str, taken: str = "", place: str = "") -> str:
	"""A Commons file name (without 'File:'): descriptive, with no characters Commons forbids."""
	parts = [(title or "").strip()]
	if place and place.lower() not in parts[0].lower():
		parts.append(place.strip())
	if taken:
		parts.append(taken.strip())
	base = re.sub(r"\s+", " ", _BAD.sub(" ", ", ".join(p for p in parts if p))).strip(" .,_")
	base = base or "Photograph"
	base = base[0].upper() + base[1:]
	suffix = "." + ext
	while len((base + suffix).encode()) > MAX_NAME_BYTES:
		base = base[:-1].rstrip()
	return base + suffix


def clean_name(name: str) -> str:
	"""What the person typed as the file name, checked: no 'File:', no forbidden characters."""
	name = re.sub(r"^\s*(file|image):", "", (name or "").strip(), flags=re.I)
	name = re.sub(r"\s+", " ", _BAD.sub(" ", name)).strip(" .,_")
	return (name[0].upper() + name[1:]) if name else ""


def split_names(text: str) -> list[str]:
	"""Category names, one per line or comma separated, without 'Category:'."""
	out = []
	for raw in re.split(r"[\n,;]", text or ""):
		n = re.sub(r"^\s*category:", "", raw.strip(), flags=re.I).strip().replace("_", " ")
		n = (n[0].upper() + n[1:]) if n else ""
		if n and n not in out:
			out.append(n)
	return out


def depicts(text: str) -> list[tuple[str, str]]:
	"""(Q id, label) for each line of the Depicts field ('Q1234' or 'Q1234 Udupi Krishna Temple')."""
	out = []
	for line in (text or "").splitlines():
		m = re.match(r"\s*(Q\d+)\b\s*(.*)", line, flags=re.I)
		if m and m.group(1).upper() not in [q for q, _ in out]:
			out.append((m.group(1).upper(), m.group(2).strip()))
	return out


def _plain(text: str) -> str:
	"""Text safe inside a template parameter: the characters that would end it are made harmless."""
	return re.sub(r"\s*\n\s*", " ", (text or "").strip()).replace("|", "{{!}}").replace("=", "&#61;")


def description_page(
	*,
	description: str,
	lang: str,
	taken: str,
	author: str,
	source: str,
	licence: str,
	categories: list[str],
	gps: str = "",
	permission: str = "",
	accession: str = "",
) -> str:
	"""The file's description page in the Information template, with licence and categories."""
	lang = lang if re.fullmatch(r"[a-z]{2,3}", lang or "") else "en"
	lines = [
		"== {{int:filedesc}} ==",
		"{{Information",
		f"|description={{{{{lang}|1={_plain(description)}}}}}",
		f"|date={_plain(taken)}",
		f"|source={source}",
		f"|author={_plain(author)}",
		f"|permission={_plain(permission)}",
		"|other versions=",
	]
	if accession:
		lines.append(f"|accession number={_plain(accession)}")
	lines.append("}}")
	m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", gps or "")
	if m:
		lines.append(f"{{{{Location|{m.group(1)}|{m.group(2)}}}}}")
	lines += ["", "== {{int:license-header}} ==", licence, ""]
	lines += [f"[[Category:{c}]]" for c in categories]
	return "\n".join(lines)


def depicts_claims(qids: list[str]) -> str:
	"""The JSON for wbeditentity that gives the file a 'depicts' (P180) statement per Wikidata item."""
	claims = [
		{
			"mainsnak": {
				"snaktype": "value",
				"property": "P180",
				"datavalue": {
					"type": "wikibase-entityid",
					"value": {"entity-type": "item", "id": q},
				},
			},
			"type": "statement",
			"rank": "normal",
		}
		for q in qids
	]
	return json.dumps({"claims": claims})
