"""Ground truth: corrected pages with their images, as an open set for training and testing OCR.

Every page a person proofread (and a second person validated) is a pair: the page image and the
text that is truly on it. Many such pairs, in Kannada, Sanskrit, Tamil or Hindi, are what better
OCR for Indian languages is made from, and what any OCR engine is measured against.

A set is one zip file:

* ``pages/<book>/<leaf>.jpg`` and ``pages/<book>/<leaf>.gt.txt``: the page image as archive.org
  serves it and its corrected text (UTF-8, as the proofreader left it);
* ``zones/<book>/<leaf>-<n>.png`` and ``.gt.txt``: each part of the page the proofreader drew
  (a column, a heading, a footnote), cropped, with its own text, when the text still splits into
  those parts. These are closest to what OCR training tools (tesstrain, kraken, Calamari) read;
* ``manifest.csv`` and ``manifest.jsonl``: one row per pair (book, page, language, status, who
  checked it, quality, image size, SHA-256 of both files);
* ``datapackage.json``: the set described as a Frictionless Data Package, with its licence;
* ``README.md`` and ``LICENSE.txt``.

The texts follow the page's line breaks; lines are not cut out of the images (line
segmentation is the training tool's job). Pure Python; Pillow crops the zones.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import json
import zipfile

from sok_resdesk.core import zones as zn

LICENCES = {
	# code (SPDX): (name, link, the line a reuser must keep)
	"CC0-1.0": (
		"CC0 1.0 Universal (public domain dedication)",
		"https://creativecommons.org/publicdomain/zero/1.0/",
		"No rights reserved: use it for anything, no credit needed (credit welcome).",
	),
	"CC-BY-4.0": (
		"Creative Commons Attribution 4.0 International",
		"https://creativecommons.org/licenses/by/4.0/",
		"Use it for anything, giving credit as below.",
	),
	"CC-BY-SA-4.0": (
		"Creative Commons Attribution-ShareAlike 4.0 International",
		"https://creativecommons.org/licenses/by-sa/4.0/",
		"Use it for anything, giving credit as below and sharing what you make from it alike.",
	),
}
MANIFEST_COLUMNS = (
	"kind",
	"image",
	"text",
	"book",
	"title",
	"leaf",
	"page_label",
	"zone",
	"language",
	"status",
	"source",
	"proofread_by",
	"validated_by",
	"quality",
	"width",
	"height",
	"characters",
	"lines",
	"image_sha256",
	"text_sha256",
	"page_url",
)


# strictness: a set may carry a page only under a licence at least as strict as its proofreaders'
RANK = {"CC0-1.0": 0, "CC-BY-4.0": 1, "CC-BY-SA-4.0": 2}


def allows(contributor: str | None, set_licence: str | None) -> bool:
	"""Whether a person's release (their licence code) lets a set carry their pages under set_licence.
	CC0 allows any set licence; CC-BY allows CC-BY and CC-BY-SA; CC-BY-SA allows only CC-BY-SA."""
	if contributor not in RANK or set_licence not in RANK:
		return False
	return RANK[set_licence] >= RANK[contributor]


def licence(code: str | None) -> dict | None:
	"""{code, name, url, terms} of a licence, or None when none is chosen yet."""
	if not code or code not in LICENCES:
		return None
	name, url, terms = LICENCES[code]
	return {"code": code, "name": name, "url": url, "terms": terms}


def zone_pairs(text: str, zones) -> list[tuple[dict, str]]:
	"""The page's text zones with their own text, or [] when they no longer match.

	A zone-by-zone OCR joins the zones' texts in reading order, a blank line between each
	(zones.join). If the proofread text still has as many such paragraphs as the page has text
	zones, each paragraph is its zone's text; otherwise (the proofreader joined or split them)
	only the whole page is a pair."""
	try:
		zones = zn.clean(zones) if zones else []
	except Exception:
		return []
	texts_zones = [z for z in zones if z.get("kind", "text") == "text"]
	if len(texts_zones) < 2:  # one zone is the page itself
		return []
	parts = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
	if len(parts) != len(texts_zones):
		return []
	return list(zip(texts_zones, parts, strict=True))


def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def _safe(part: str) -> str:
	"""An archive.org identifier as a folder name (they are already safe; this keeps them so)."""
	out = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(part))
	return out.strip(".") or "_"


def _size(image: bytes) -> tuple[int, int]:
	from PIL import Image

	with Image.open(io.BytesIO(image)) as img:
		return img.width, img.height


def crop(image: bytes, zone: dict) -> bytes:
	"""One zone of a page image, as PNG."""
	from PIL import Image, ImageOps

	with Image.open(io.BytesIO(image)) as img:
		img = ImageOps.exif_transpose(img)
		part = img.crop(zn.pixels(zone, img.width, img.height))
		if part.mode not in ("L", "RGB"):
			part = part.convert("RGB")
		buf = io.BytesIO()
		part.save(buf, format="PNG", optimize=True)
		return buf.getvalue()


def _text_bytes(text: str) -> bytes:
	return ((text or "").rstrip("\n") + "\n").encode("utf-8")


def _row(kind: str, image_path: str, text_path: str, page: dict, zone_no, image: bytes, text: str, size):
	return {
		"kind": kind,
		"image": image_path,
		"text": text_path,
		"book": page["item"],
		"title": page.get("title") or "",
		"leaf": page["leaf"],
		"page_label": page.get("page_label") or "",
		"zone": zone_no if zone_no is not None else "",
		"language": page.get("language") or "",
		"status": page.get("status") or "",
		"source": page.get("source") or "",
		"proofread_by": page.get("proofread_by") or "",
		"validated_by": page.get("validated_by") or "",
		"quality": page.get("quality") if page.get("quality") is not None else "",
		"width": size[0],
		"height": size[1],
		"characters": len(text or ""),
		"lines": len([x for x in (text or "").splitlines() if x.strip()]),
		"image_sha256": _sha256(image),
		"text_sha256": _sha256(_text_bytes(text)),
		"page_url": page.get("page_url") or "",
	}


def write(path: str, pages, image_of, meta: dict, with_zones: bool = True, log=None) -> dict:
	"""Write a ground-truth set to the zip at `path`.

	`pages`: dicts {item, title, leaf, page_label, text, zones, language, status, source,
	proofread_by, validated_by, quality, page_url}; `image_of(item, leaf)` → the page image
	(bytes), or raises to skip the page; `meta`: {title, organisation, url, licence (code or
	None), attribution, created}. Returns the counts and languages."""
	rows, skipped, books, languages = [], 0, set(), {}
	with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
		for page in pages:
			try:
				image = image_of(page["item"], page["leaf"])
				size = _size(image)
			except Exception as e:
				skipped += 1
				if log:
					log(f"{page['item']} page {page['leaf']}: left out ({str(e)[:120]})")
				continue
			book = _safe(page["item"])
			stem = f"{book}/{int(page['leaf']):04d}"
			z.writestr(f"pages/{stem}.jpg", image, compress_type=zipfile.ZIP_STORED)
			z.writestr(f"pages/{stem}.gt.txt", _text_bytes(page["text"]))
			rows.append(
				_row(
					"page", f"pages/{stem}.jpg", f"pages/{stem}.gt.txt", page, None, image, page["text"], size
				)
			)
			books.add(page["item"])
			for code in [
				x for x in str(page.get("language") or "").replace(";", ",").split(",") if x.strip()
			]:
				languages[code.strip()] = languages.get(code.strip(), 0) + 1
			if not with_zones:
				continue
			for n, (zone, text) in enumerate(zone_pairs(page["text"], page.get("zones")), start=1):
				try:
					part = crop(image, zone)
					part_size = _size(part)
				except Exception:
					continue
				zstem = f"{stem}-{n:02d}"
				z.writestr(f"zones/{zstem}.png", part, compress_type=zipfile.ZIP_STORED)
				z.writestr(f"zones/{zstem}.gt.txt", _text_bytes(text))
				rows.append(
					_row(
						"zone", f"zones/{zstem}.png", f"zones/{zstem}.gt.txt", page, n, part, text, part_size
					)
				)
		counts = {
			"pages": sum(1 for r in rows if r["kind"] == "page"),
			"zones": sum(1 for r in rows if r["kind"] == "zone"),
			"books": len(books),
			"skipped": skipped,
			"languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
		}
		z.writestr("manifest.csv", manifest_csv(rows))
		z.writestr("manifest.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
		z.writestr("datapackage.json", json.dumps(datapackage(meta, counts), indent=2, ensure_ascii=False))
		z.writestr("README.md", readme(meta, counts))
		z.writestr("LICENSE.txt", licence_text(meta))
	return counts


def manifest_csv(rows: list[dict]) -> str:
	buf = io.StringIO()
	w = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
	w.writeheader()
	w.writerows(rows)
	return buf.getvalue()


def datapackage(meta: dict, counts: dict) -> dict:
	"""The set as a Frictionless Data Package (https://specs.frictionlessdata.io/data-package/)."""
	lic = licence(meta.get("licence"))
	out = {
		"profile": "data-package",
		"name": _safe(meta.get("name") or "ground-truth").lower(),
		"title": meta.get("title") or "OCR ground truth",
		"description": (
			f"{counts['pages']} proofread page images with their corrected text"
			+ (f", and {counts['zones']} page parts" if counts.get("zones") else "")
			+ f", from {counts['books']} books."
		),
		"created": meta.get("created") or _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"homepage": meta.get("url") or "",
		"keywords": ["OCR", "ground truth", *counts.get("languages", {}).keys()],
		"contributors": [{"title": meta.get("organisation") or "Research Desk", "role": "publisher"}],
		"resources": [
			{
				"name": "manifest",
				"path": "manifest.csv",
				"format": "csv",
				"mediatype": "text/csv",
				"encoding": "utf-8",
				"schema": {"fields": [{"name": c, "type": _type(c)} for c in MANIFEST_COLUMNS]},
			}
		],
	}
	if lic:
		out["licenses"] = [{"name": lic["code"], "path": lic["url"], "title": lic["name"]}]
	return out


def _type(column: str) -> str:
	return "integer" if column in ("leaf", "width", "height", "characters", "lines") else "string"


def readme(meta: dict, counts: dict) -> str:
	lic = licence(meta.get("licence"))
	langs = ", ".join(f"{k} ({v} pages)" for k, v in counts.get("languages", {}).items()) or "n/a"
	lines = [
		f"# {meta.get('title') or 'OCR ground truth'}",
		"",
		f"From {meta.get('organisation') or 'a Research Desk library'}"
		+ (f" ({meta['url']})" if meta.get("url") else "")
		+ f", made {meta.get('created') or ''}.",
		"",
		f"- {counts['pages']} page images with their text, corrected by people (proofread"
		+ (", then checked by a second person" if meta.get("validated_only") else " or validated")
		+ ")",
		f"- {counts.get('zones', 0)} page parts (columns, headings, notes) cut out with their own text",
		f"- {counts['books']} books; languages (ISO 639-3): {langs}",
		"",
		"## Files",
		"",
		"- `pages/<book>/<page>.jpg` and `.gt.txt`: a page image and its text (UTF-8). `<book>` is",
		"  the archive.org identifier; `<page>` counts the book's page images from 0.",
		"- `zones/<book>/<page>-<n>.png` and `.gt.txt`: part n of the page, in reading order.",
		"- `manifest.csv` / `manifest.jsonl`: one row per pair, with the book, page, language,",
		"  who checked it, image size and SHA-256 checksums of both files.",
		"- `datapackage.json`: the same, as a Frictionless Data Package.",
		"",
		"Texts keep the page's line breaks; lines are not cut out of the images. Training tools such",
		"as tesstrain or kraken segment lines themselves; for testing an OCR engine, compare its",
		"output for each image with the `.gt.txt` (character error rate).",
		"",
		"## Licence",
		"",
	]
	if lic:
		lines += [f"{lic['name']} ({lic['code']}): {lic['url']}", "", lic["terms"]]
		if meta.get("attribution"):
			lines += ["", f"Credit: {meta['attribution']}"]
		lines += [
			"",
			"The licence covers the corrected texts and this arrangement of them. The page images",
			"are reproduced from the books' scans; check each book's own rights (its page_url) too.",
		]
	else:
		lines += [
			"No licence has been chosen for this set yet. It is for the library's own use and must",
			"not be shared further until one is.",
		]
	return "\n".join(lines) + "\n"


def licence_text(meta: dict) -> str:
	lic = licence(meta.get("licence"))
	if not lic:
		return "No licence chosen yet: not for redistribution.\n"
	out = f"{lic['name']}\n{lic['url']}\n\n{lic['terms']}\n"
	if meta.get("attribution"):
		out += f"\nCredit: {meta['attribution']}\n"
	return out
