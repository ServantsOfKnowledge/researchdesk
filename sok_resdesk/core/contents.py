"""A book's table of contents, read from the OCR text of its contents pages.

Pure rules, no database: find which of the first pages are the contents, turn their lines into
entries (title, printed page, level), say how sure we are, and work out which page image each
printed page number is. The Frappe side (contents.py) stores the result as a draft for a person.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

# what a contents page is headed with, lower case (English and the Indian languages of the library)
HEADINGS = (
	"table of contents",
	"contents",
	"list of contents",
	"index of contents",
	"ವಿಷಯ ಸೂಚಿ",
	"ವಿಷಯ ಸೂಚಿಕೆ",
	"ವಿಷಯಾನುಕ್ರಮಣಿಕೆ",
	"ಅನುಕ್ರಮಣಿಕೆ",
	"ಪರಿವಿಡಿ",
	"ವಿಷಯಗಳು",
	"विषय सूची",
	"विषय-सूची",
	"विषयसूची",
	"अनुक्रमणिका",
	"विषयानुक्रमणिका",
	"அட்டவணை",
	"பொருளடக்கம்",
	"உள்ளடக்கம்",
	"విషయ సూచిక",
	"విషయ సూచీ",
	"ഉള്ളടക്കം",
	"বিষয়সূচি",
	"સૂચિ",
)
FRONT_PAGES = 40  # contents are looked for among this many pages at most
CONTINUES = 6  # a contents list runs over this many pages at most
ROMAN = re.compile(r"^[ivxlc]{1,7}$")
# dots (or middle dots, ellipses, underscores) between a title and its page, however OCR spaced them
LEADER = re.compile(r"(?:\s*[.·…_]\s*){2,}")
ENTRY = re.compile(
	r"""^\s*(?P<title>\S.*?\S|\S)       # the title, with its own numbering
		(?:\s*…\s*|\s{2,}|\t)           # a leader, or a gap
		(?P<page>\d{1,4}|[ivxlc]{1,7})\s*$""",
	re.X,
)
BARE_ENTRY = re.compile(r"^\s*(?P<title>\S.*?[^\s\d.])\s+(?P<page>\d{1,4})\s*$")  # "Title 12", no leader
NUMBERING = re.compile(r"^\s*(?P<n>\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s")


def digits(text: str) -> str:
	"""The page number in ASCII digits, whatever script the digits are in (೧೨ → 12, १२ → 12)."""
	return "".join(str(unicodedata.decimal(c)) if c.isdigit() else c for c in text)


def _norm(line: str) -> str:
	return re.sub(r"[\s:.\-–—_]+", " ", line.casefold()).strip()


def is_heading(line: str) -> bool:
	line = _norm(line)
	return any(line == h or (line.startswith(h) and len(line) <= len(h) + 4) for h in HEADINGS)


def _lines(text: str) -> list[str]:
	return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def entry_of(line: str) -> dict | None:
	"""{"title", "page", "level"} for a line that reads 'Title ..... 12', else None."""
	line = LEADER.sub(" … ", line)
	m = ENTRY.match(line)
	if m is None:
		# no leader: "Title 12" counts only for a real title (a few words) and a printed page
		m = BARE_ENTRY.match(line)
		if m is None or len(m["title"].split()) < 2:
			return None
	title = m["title"].strip(" …._-–—")
	page = digits(m["page"])
	if not title or title.isdigit() or (not page.isdigit() and not ROMAN.match(page)):
		return None
	numbering = NUMBERING.match(title)
	level = numbering["n"].count(".") + 1 if numbering else 1
	return {"title": title, "page": page, "level": level}


def density(text: str) -> tuple[int, int]:
	"""(lines that read as entries, lines in all) of a page, not counting its heading."""
	lines = [ln for ln in _lines(text) if not is_heading(ln)]
	return sum(1 for ln in lines if entry_of(ln)), len(lines)


def find_pages(pages: list[dict]) -> dict:
	"""Which pages are the contents: {"leaves": [...], "heading": bool}. `pages` = [{leaf, text}] in order.

	The page with the heading starts it (even when OCR spoiled its lines); the next pages follow while
	most of their lines are entries. With no heading, the page of the front that is most all entries."""
	front = pages[: max(12, min(FRONT_PAGES, len(pages) // 8))]
	scored = []
	for p in front:
		hits, total = density(p.get("text") or "")
		head = any(is_heading(ln) for ln in _lines(p.get("text") or "")[:6])
		scored.append((p["leaf"], hits, total, head))
	start = next((i for i, s in enumerate(scored) if s[3]), None)
	heading = start is not None
	if start is None:
		best = max(range(len(scored)), key=lambda i: scored[i][1], default=None)
		if best is None or scored[best][1] < 5 or scored[best][1] < 0.6 * max(scored[best][2], 1):
			return {"leaves": [], "heading": False}
		start = best
	leaves = [scored[start][0]]
	for _leaf, hits, total, _head in scored[start + 1 : start + 1 + CONTINUES]:
		if total and hits >= 0.5 * total and hits >= 3:
			leaves.append(_leaf)
		else:
			break
	return {"leaves": leaves, "heading": heading}


def parse(texts: list[str]) -> list[dict]:
	"""Entries from the text of the contents pages, in order. A title wrapped over two lines is joined."""
	entries: list[dict] = []
	pending: list[str] = []
	for text in texts:
		for line in _lines(text):
			if is_heading(line):
				continue
			entry = entry_of(line)
			if entry is None:
				if len(pending) < 2 and len(line) < 120:
					pending.append(line)
				continue
			if pending and not NUMBERING.match(entry["title"]) and entry["title"][:1].islower():
				entry["title"] = " ".join([*pending, entry["title"]])
			pending = []
			entries.append(entry)
		pending = []
	return entries


def quality(entries: list[dict], lines: int) -> dict:
	"""How much to trust the entries: {"score": 0-100, "unclear": bool, "why": str}."""
	n = len(entries)
	pages = [int(e["page"]) for e in entries if e["page"].isdigit()]
	steps = list(zip(pages, pages[1:], strict=False))
	ordered = sum(1 for a, b in steps if b >= a) / len(steps) if steps else 0.0
	share = n / lines if lines else 0.0
	score = round(100 * min(1.0, n / 8) * (0.5 * ordered + 0.5 * min(1.0, share / 0.6)))
	why = (
		"fewer than three entries"
		if n < 3
		else "the page numbers do not run in order"
		if ordered < 0.75
		else "many lines were not read as entries"
		if share < 0.4
		else ""
	)
	return {"score": score, "unclear": bool(why), "why": why}


def _key(title: str) -> str:
	return re.sub(r"[\W_]+", "", title.casefold())[:15]


def leaves_for(entries: list[dict], labels: dict[int, str], texts: dict[int, str], after: int) -> list[dict]:
	"""Each entry with the page image it points to ("leaf", counted from 0, or None).

	By the page labels the book has when it has them; else by the offset between printed page and
	page image, found by looking where the first titles start after the contents pages."""
	by_label = {str(v).strip(): k for k, v in labels.items() if str(v).strip()}
	offsets = Counter()
	for e in entries[:8]:
		if not e["page"].isdigit() or len(_key(e["title"])) < 5:
			continue
		for leaf in sorted(k for k in texts if k > after)[:80]:
			if _key(e["title"]) in _key(" ".join(_lines(texts[leaf])[:4])):
				offsets[leaf - int(e["page"])] += 1
				break
	offset = offsets.most_common(1)[0][0] if offsets else None
	out = []
	for e in entries:
		leaf = by_label.get(e["page"])
		if leaf is None and offset is not None and e["page"].isdigit():
			leaf = max(0, int(e["page"]) + offset)
		out.append({**e, "leaf": leaf})
	return out
