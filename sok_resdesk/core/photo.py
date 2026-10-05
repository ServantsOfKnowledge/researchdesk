"""Photographs: what a picture file says about itself (EXIF) and what a person says about it.

A photograph is one image with its own details: when and where it was taken (from the camera's
EXIF, if it has them), who took it, who and what is in it, and a SHA-256 of the original so its
fixity can be checked for as long as it is kept. Nothing here imports Frappe; Pillow reads the file.
"""

from __future__ import annotations

import hashlib
import json
import re

IFD_EXIF, IFD_GPS = 0x8769, 0x8825
T_MAKE, T_MODEL, T_ARTIST, T_DESC, T_COPYRIGHT = 0x010F, 0x0110, 0x013B, 0x010E, 0x8298
T_TAKEN, T_DIGITISED, T_DATETIME = 0x9003, 0x9004, 0x0132


def sha256_of(path: str) -> str:
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(1 << 20), b""):
			h.update(block)
	return h.hexdigest()


def _clean(value) -> str:
	if isinstance(value, bytes):
		value = value.decode("utf-8", "replace")
	return re.sub(r"[\x00-\x1f]+", " ", str(value or "")).strip()


def exif_date(value: str) -> str:
	"""`2019:03:14 10:22:05` → `2019-03-14`; anything else → ''."""
	m = re.match(r"(\d{4})[:\-](\d\d)[:\-](\d\d)", _clean(value))
	if not m or m.group(1) == "0000":
		return ""
	return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _degrees(dms, ref) -> float | None:
	try:
		d, m, s = (float(x) for x in dms)
	except (TypeError, ValueError):
		return None
	deg = d + m / 60 + s / 3600
	return -deg if _clean(ref).upper() in ("S", "W") else deg


def exif_info(path: str) -> dict:
	"""{"taken_on", "camera", "photographer", "description", "copyright", "lat", "lon", "width",
	"height"} from the file (missing parts left out). Never raises: a file without EXIF gives its size."""
	from PIL import Image

	out: dict = {}
	try:
		with Image.open(path) as im:
			out["width"], out["height"] = im.size
			exif = im.getexif()
			tags = dict(exif)
			sub = exif.get_ifd(IFD_EXIF) if hasattr(exif, "get_ifd") else {}
			gps = exif.get_ifd(IFD_GPS) if hasattr(exif, "get_ifd") else {}
	except Exception:
		return out
	taken = exif_date(sub.get(T_TAKEN) or sub.get(T_DIGITISED) or tags.get(T_DATETIME))
	if taken:
		out["taken_on"] = taken
	camera = " ".join(x for x in (_clean(tags.get(T_MAKE)), _clean(tags.get(T_MODEL))) if x)
	if camera:
		out["camera"] = camera
	for key, tag in (("photographer", T_ARTIST), ("description", T_DESC), ("copyright", T_COPYRIGHT)):
		if _clean(tags.get(tag)):
			out[key] = _clean(tags.get(tag))
	lat = _degrees(gps.get(2), gps.get(1))
	lon = _degrees(gps.get(4), gps.get(3))
	if lat is not None and lon is not None and (lat or lon):
		out["lat"], out["lon"] = round(lat, 6), round(lon, 6)
	return out


def photo_id(rel_path: str) -> str:
	"""`1931/Mysore palace.jpg` → `ph-1931-Mysore-palace`."""
	base = re.sub(r"\.[A-Za-z0-9]+$", "", rel_path.strip("/"))
	return ("ph-" + re.sub(r"[^\w.-]+", "-", base, flags=re.UNICODE).strip("-"))[:140]


def sidecar(raw: bytes | None, stem: str, exif: dict) -> tuple[dict, dict]:
	"""A photograph's `<name>.json` and its EXIF → (details in IA's names, the photograph's own fields).

	Keys in the json: title, creator (the photographer), date, description, subject (tags), rights,
	licenseurl, language, and `photo`: {people, place, event, depicts}. A person's words win over
	the camera's."""
	try:
		data = json.loads(raw.decode("utf-8-sig")) if raw else {}
	except ValueError:
		data = {}
	data = data if isinstance(data, dict) else {}
	own = data.pop("photo", None) if isinstance(data.get("photo"), dict) else (data.pop("photo", None) and {})
	own = own or {}
	meta = dict(data)
	meta.setdefault("title", re.sub(r"[_]+", " ", stem).strip() or stem)
	if exif.get("photographer"):
		meta.setdefault("creator", exif["photographer"])
	if exif.get("taken_on"):
		meta.setdefault("date", exif["taken_on"])
	if exif.get("description"):
		meta.setdefault("description", exif["description"])
	if exif.get("copyright"):
		meta.setdefault("rights", exif["copyright"])
	meta["mediatype"] = "image"
	fields: dict = {}
	for key in ("people", "depicts"):
		v = own.get(key)
		if isinstance(v, list):
			v = "\n".join(str(x) for x in v)
		if v:
			fields[f"ph_{key}"] = str(v)
	for key in ("place", "event"):
		if own.get(key):
			fields[f"ph_{key}"] = str(own[key])
	if exif.get("taken_on"):
		fields["ph_taken_on"] = own.get("taken_on") or exif["taken_on"]
	elif own.get("taken_on"):
		fields["ph_taken_on"] = str(own["taken_on"])
	if exif.get("camera"):
		fields["ph_camera"] = exif["camera"]
	if "lat" in exif:
		fields["ph_gps"] = f"{exif['lat']}, {exif['lon']}"
	if exif.get("width"):
		fields["ph_dimensions"] = f"{exif['width']} × {exif['height']} px"
	return meta, fields
