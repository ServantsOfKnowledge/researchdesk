"""Which OCR page is which page image: archive.org's scan data (scandata.xml).

archive.org's OCR (hOCR, and the search text made from it) has one page for every leaf that was
scanned, including the leaves left out of the book as readers see it: the colour card, a
blank back cover, a duplicate. Its page images (…/page/n0.jpg, n1…) and its PDF count only the
pages shown. Without scandata.xml the two counts drift apart at the first leaf left out, and a
page's text would sit next to the following page's image.

scandata.xml lists every leaf in order with `addToAccessFormats` (false = left out). The k-th
OCR page is the k-th leaf when the OCR has as many pages as the scan data; then a page shown is
numbered by the pages shown before it, and the leaves left out lose their text.

Pure Python (standard library only).
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET


def parse(xml: bytes | None) -> list[tuple[int, bool]]:
	"""[(leafNum, shown)] for every leaf, in scan order ([] when unreadable)."""
	if not xml:
		return []
	try:
		root = ET.fromstring(xml)
	except ET.ParseError:
		return []
	leaves = []
	for n, page in enumerate(root.iter("page")):
		try:
			leaf = int(page.get("leafNum", n))
		except ValueError:
			leaf = n
		flag = (page.findtext("addToAccessFormats") or "true").strip().lower()
		leaves.append((leaf, flag != "false"))
	return leaves


def from_zip(data: bytes | None) -> bytes | None:
	"""scandata.xml out of a scandata.zip (older scans keep it there)."""
	if not data:
		return None
	try:
		with zipfile.ZipFile(io.BytesIO(data)) as z:
			for name in z.namelist():
				if name.endswith("scandata.xml"):
					return z.read(name)
	except (zipfile.BadZipFile, OSError):
		return None
	return None


def file_name(identifier: str, names: list[str]) -> str:
	"""The item's scan data file among its files: …_scandata.xml, scandata.xml or scandata.zip."""
	names = list(names)
	for want in (f"{identifier}_scandata.xml", "scandata.xml"):
		if want in names:
			return want
	for name in names:
		if name.endswith("_scandata.xml"):
			return name
	return "scandata.zip" if "scandata.zip" in names else ""


def leaf_map(leaves: list[tuple[int, bool]], ocr_pages: int) -> list[int | None] | None:
	"""For each OCR page (0…ocr_pages-1) the page shown it belongs to, or None for a leaf left out.
	None when no mapping is needed or known (the OCR already counts the pages shown only)."""
	if not leaves or ocr_pages != len(leaves) or all(shown for _, shown in leaves):
		return None
	out, n = [], 0
	for _, shown in leaves:
		out.append(n if shown else None)
		n += shown
	return out


def labels(page_numbers: dict | None, leaves: list[tuple[int, bool]] | None = None) -> dict[int, str]:
	"""{OCR page: printed number} from page_numbers.json. Its entries name their leaf (leafNum)
	when archive.org made them from the scan data; otherwise they are in OCR page order."""
	entries = (page_numbers or {}).get("pages", []) or []
	if leaves and any("leafNum" in e for e in entries):
		where = {leaf: k for k, (leaf, _) in enumerate(leaves)}
		found = {}
		for e in entries:
			k = where.get(_int(e.get("leafNum")))
			if k is not None:
				found[k] = str(e.get("pageNumber") or "")
		if found:
			return found
	return {n: str(e.get("pageNumber") or "") for n, e in enumerate(entries)}


def pages(
	texts: list[str],
	page_numbers: dict | None = None,
	leaves: list[tuple[int, bool]] | None = None,
) -> list[dict]:
	"""OCR pages' texts (in OCR page order, one per OCR page, empty ones included) → the book's
	pages [{leaf, label, text}], `leaf` counting the pages shown (…/page/n{leaf}.jpg)."""
	mapping = leaf_map(leaves or [], len(texts))
	names = labels(page_numbers, leaves)
	out = []
	for k, text in enumerate(texts):
		text = (text or "").strip()
		leaf = k if mapping is None else mapping[k]
		if text and leaf is not None:
			out.append({"leaf": leaf, "label": names.get(k, ""), "text": text})
	return out


def _int(value) -> int | None:
	try:
		return int(value)
	except (TypeError, ValueError):
		return None
