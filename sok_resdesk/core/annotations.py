"""Annotations: the W3C Web Annotation model, anchoring notes in page text, and exports. Pure Python.

A note points at a page of a book (its leaf) and, inside it, either at a passage of the page
text or at a region of the page image:

* a passage is kept two ways, as W3C recommends: by position (start and end characters in the
  page text, a TextPositionSelector) and by the words themselves with a little context on each
  side (a TextQuoteSelector). When the page text changes (better OCR, a proofreader's
  correction) the position no longer fits, and the note finds its words again by the quote;
* a region is a rectangle on the page image in percent of its size (a FragmentSelector,
  `xywh=percent:x,y,w,h`), so it fits whatever size the image is shown at.

https://www.w3.org/TR/annotation-model/
"""

from __future__ import annotations

import csv
import io
import re

from sok_resdesk.core import wikidata

MOTIVATIONS = {
	# the reader's word: the W3C motivation
	"Highlight": "highlighting",
	"Comment": "commenting",
	"Tag": "tagging",
	"Question": "questioning",
	"Link": "linking",
	"OCR error": "editing",
}
CONTEXT = 32  # characters of context kept on each side of a quote


def quote_selector(text: str, start: int, end: int) -> dict:
	"""{exact, prefix, suffix} for text[start:end]."""
	start, end = max(0, start), min(len(text), end)
	return {
		"exact": text[start:end],
		"prefix": text[max(0, start - CONTEXT) : start],
		"suffix": text[end : end + CONTEXT],
	}


def anchor(
	text: str, start: int | None, end: int | None, exact: str, prefix: str = "", suffix: str = ""
) -> tuple[int, int] | None:
	"""Where a passage note sits in `text` now: its position if the words are still there, else
	the best place the quoted words appear (the one whose context matches most), else None (the
	passage is gone: the note is shown as detached)."""
	if not exact:
		return None
	if start is not None and end is not None and text[start:end] == exact:
		return start, end
	best, best_score = None, -1
	for m in re.finditer(re.escape(exact), text):
		s, e = m.start(), m.end()
		before, after = text[max(0, s - len(prefix)) : s], text[e : e + len(suffix)]
		score = _common_suffix(before, prefix) + _common_prefix(after, suffix)
		if start is not None:
			score -= abs(s - start) / 10_000  # ties: the one nearest where it was
		if score > best_score:
			best, best_score = (s, e), score
	return best


def _common_prefix(a: str, b: str) -> int:
	n = 0
	for x, y in zip(a, b, strict=False):
		if x != y:
			break
		n += 1
	return n


def _common_suffix(a: str, b: str) -> int:
	return _common_prefix(a[::-1], b[::-1])


def region(x: float, y: float, w: float, h: float) -> str:
	"""A rectangle on the page image, in percent (0-100), as a W3C media fragment."""

	def clip(v: float) -> float:
		return round(min(100.0, max(0.0, float(v))), 2)

	x, y = clip(x), clip(y)
	return f"xywh=percent:{x:g},{y:g},{clip(min(w, 100 - x)):g},{clip(min(h, 100 - y)):g}"


def parse_region(value: str) -> tuple[float, float, float, float] | None:
	m = re.fullmatch(r"xywh=percent:([\d.]+),([\d.]+),([\d.]+),([\d.]+)", value or "")
	return tuple(float(g) for g in m.groups()) if m else None


def to_w3c(note: dict, page_url: str, image_url: str = "", creator_url: str = "") -> dict:
	"""One note as a W3C Web Annotation (JSON-LD). `page_url` identifies the page (its link in the
	page reader, or the page's ARK); the body carries the comment, tags and link."""
	motivation = MOTIVATIONS.get(note.get("kind") or "Comment", "commenting")
	bodies = []
	if note.get("body"):
		bodies.append(
			{
				"type": "TextualBody",
				"value": note["body"],
				"format": "text/plain",
				"purpose": "commenting" if motivation != "questioning" else "questioning",
			}
		)
	for tag in split_tags(note.get("tags")):
		bodies.append({"type": "TextualBody", "value": tag, "purpose": "tagging"})
	entity = wikidata.qid(note.get("entity"))
	if entity:  # what the passage is about (W3C model §3.3.5: purpose on a SpecificResource)
		bodies.append(
			{"type": "SpecificResource", "source": wikidata.entity_uri(entity), "purpose": "identifying"}
		)
	if note.get("link") and not (entity and wikidata.qid(note["link"]) == entity):
		bodies.append({"type": "SpecificResource", "source": note["link"], "purpose": "identifying"})
	target: dict = {"source": page_url}
	if note.get("region"):
		target = {
			"source": image_url or page_url,
			"selector": {
				"type": "FragmentSelector",
				"conformsTo": "http://www.w3.org/TR/media-frags/",
				"value": note["region"],
			},
		}
	elif note.get("exact"):
		target["selector"] = [
			{
				"type": "TextQuoteSelector",
				"exact": note["exact"],
				"prefix": note.get("prefix") or "",
				"suffix": note.get("suffix") or "",
			},
			{"type": "TextPositionSelector", "start": note.get("start") or 0, "end": note.get("end") or 0},
		]
	out = {
		"@context": "http://www.w3.org/ns/anno.jsonld",
		"id": note.get("id") or "",
		"type": "Annotation",
		"motivation": motivation,
		"created": note.get("created") or "",
		"modified": note.get("modified") or "",
		"target": target,
	}
	if creator_url or note.get("creator"):
		out["creator"] = {
			"type": "Person",
			**({"id": creator_url} if creator_url else {}),
			"name": note.get("creator") or "",
		}
	if bodies:
		out["body"] = bodies[0] if len(bodies) == 1 else bodies
	return out


def page_collection(notes: list[dict], collection_id: str) -> dict:
	"""Notes as a W3C AnnotationPage (all on one page of results)."""
	return {
		"@context": "http://www.w3.org/ns/anno.jsonld",
		"id": collection_id,
		"type": "AnnotationPage",
		"items": notes,
	}


def split_tags(value) -> list[str]:
	if not value:
		return []
	if isinstance(value, (list, tuple)):
		parts = value
	else:
		parts = re.split(r"[,\n]", str(value))
	return list(dict.fromkeys(t.strip() for t in parts if t and t.strip()))


def to_markdown(notes: list[dict]) -> str:
	"""Notes grouped by book, each with the cited page and the quoted words: for a writing tool."""
	out, book = [], None
	for n in notes:
		if n.get("book_title") != book:
			book = n.get("book_title")
			out.append(f"\n## {book}\n")
			if n.get("book_citation"):
				out.append(f"{n['book_citation']}\n")
		where = n.get("page") or ""
		line = f"- **{where}**" if where else "-"
		if n.get("exact"):
			line += f" “{n['exact']}”"
		elif n.get("region"):
			line += " (a region of the page image)"
		if n.get("body"):
			line += f": {n['body']}"
		tags = split_tags(n.get("tags"))
		if tags:
			line += " " + " ".join(f"#{t.replace(' ', '_')}" for t in tags)
		if wikidata.qid(n.get("entity")):
			q = wikidata.qid(n.get("entity"))
			line += f" [{n.get('entity_label') or q}]({wikidata.page_url(q)})"
		if n.get("link"):
			line += f" <{n['link']}>"
		if n.get("url"):
			line += f" [{where or 'page'}]({n['url']})"
		out.append(line)
	return "\n".join(out).strip() + "\n"


CSV_COLUMNS = (
	"book",
	"page",
	"kind",
	"quote",
	"note",
	"tags",
	"link",
	"wikidata",
	"wikidata_name",
	"who_can_see",
	"url",
	"created",
)


def to_csv(notes: list[dict]) -> str:
	buf = io.StringIO()
	w = csv.writer(buf)
	w.writerow(CSV_COLUMNS)
	for n in notes:
		w.writerow(
			[
				n.get("book_title") or "",
				n.get("page") or "",
				n.get("kind") or "",
				n.get("exact") or ("(region)" if n.get("region") else ""),
				n.get("body") or "",
				", ".join(split_tags(n.get("tags"))),
				n.get("link") or "",
				wikidata.qid(n.get("entity")) or "",
				n.get("entity_label") or "",
				n.get("visibility") or "",
				n.get("url") or "",
				n.get("created") or "",
			]
		)
	return buf.getvalue()


# -- the other way: a Web Annotation from another tool → a note (the Annotation Protocol) ----------

KIND_OF = {v: k for k, v in MOTIVATIONS.items()}
_LEAF_PATTERNS = (
	re.compile(r"[?&]page=(\d+)"),  # …/library/item/<id>?page=12
	re.compile(r"/n(\d+)(?:\.jpg)?(?:$|[/?#])"),  # an ARK …/n12, or archive.org …/page/n12(.jpg)
)


class AnnotationError(ValueError):
	pass


def leaf_of(source: str) -> int | None:
	"""The page (leaf, from 0) a target's source names: the page reader's link, a page ARK, or
	archive.org's page or page image."""
	for pattern in _LEAF_PATTERNS:
		m = pattern.search(source or "")
		if m:
			return int(m.group(1))
	return None


def _list(value) -> list:
	if value is None:
		return []
	return value if isinstance(value, list) else [value]


def from_w3c(anno: dict) -> dict:
	"""A W3C Web Annotation (JSON-LD, as another tool POSTs it) → the note's fields:
	{kind, body, tags, link, entity, leaf, exact, prefix, suffix, start, end, region}.
	Raises AnnotationError with what is wrong."""
	if not isinstance(anno, dict) or "Annotation" not in _list(anno.get("type")):
		raise AnnotationError("Send a W3C Web Annotation (type: Annotation).")
	motivation = (_list(anno.get("motivation")) or ["commenting"])[0]
	kind = KIND_OF.get(motivation.replace("oa:", ""), "Comment")
	note: dict = {"kind": kind, "body": "", "tags": [], "link": "", "entity": ""}
	for b in _list(anno.get("body")):
		if isinstance(b, str):
			b = {"id": b}
		purpose = (b.get("purpose") or "").replace("oa:", "")
		value = b.get("value")
		if value is not None and (b.get("type") in (None, "TextualBody", "oa:TextualBody")):
			if purpose == "tagging":
				note["tags"].append(str(value)[:100])
			else:
				note["body"] = (note["body"] + "\n\n" + str(value)).strip()
			continue
		ref = b.get("source") or b.get("id") or ""
		if not ref:
			continue
		q = wikidata.qid(ref)
		if q and not note["entity"]:
			note["entity"] = q
		elif str(ref).startswith(("https://", "http://")):
			note["link"] = str(ref)[:500]
	targets = _list(anno.get("target"))
	if not targets:
		raise AnnotationError("The annotation needs a target: the page it is on.")
	target = targets[0]
	if isinstance(target, str):
		target = {"source": target}
	source = target.get("source") or target.get("id") or ""
	note["leaf"] = leaf_of(source)
	if note["leaf"] is None:
		raise AnnotationError("The target's source must be a page of the book (its page link or page ARK).")
	for sel in _list(target.get("selector")):
		kind_of = (sel.get("type") or "").replace("oa:", "")
		if kind_of == "TextQuoteSelector":
			note.update(
				exact=sel.get("exact") or "", prefix=sel.get("prefix") or "", suffix=sel.get("suffix") or ""
			)
		elif kind_of == "TextPositionSelector":
			note.update(start=int(sel.get("start") or 0), end=int(sel.get("end") or 0))
		elif kind_of == "FragmentSelector":
			r = parse_region(sel.get("value") or "")
			if not r:
				raise AnnotationError("A FragmentSelector must be xywh=percent:x,y,w,h.")
			note["region"] = region(*r)
	if not (note.get("exact") or note.get("region") or note.get("end")):  # a position alone will do
		raise AnnotationError(
			"Say where on the page: a TextQuoteSelector, TextPositionSelector or FragmentSelector."
		)
	note["tags"] = ", ".join(split_tags(note["tags"]))
	return note


def collection_page(
	items: list[dict], container: str, page: int, total: int, per_page: int, embed: bool = True
) -> dict:
	"""One page of an AnnotationCollection (Annotation Protocol §4.2)."""
	last = max(0, (total - 1) // per_page)
	out = {
		"@context": "http://www.w3.org/ns/anno.jsonld",
		"id": f"{container}?page={page}" + ("" if embed else "&iris=1"),
		"type": "AnnotationPage",
		"partOf": {"id": container, "total": total},
		"startIndex": page * per_page,
		"items": items if embed else [i["id"] for i in items],
	}
	if page < last:
		out["next"] = f"{container}?page={page + 1}" + ("" if embed else "&iris=1")
	if page > 0:
		out["prev"] = f"{container}?page={page - 1}" + ("" if embed else "&iris=1")
	return out


def collection(container: str, label: str, total: int, per_page: int, embed: bool = True) -> dict:
	"""The container itself: an AnnotationCollection with links to its first and last pages."""
	suffix = "" if embed else "&iris=1"
	out = {
		"@context": ["http://www.w3.org/ns/anno.jsonld", "http://www.w3.org/ns/ldp.jsonld"],
		"id": container,
		"type": ["BasicContainer", "AnnotationCollection"],
		"label": label,
		"total": total,
	}
	if total:
		out["first"] = f"{container}?page=0{suffix}"
		out["last"] = f"{container}?page={max(0, (total - 1) // per_page)}{suffix}"
	return out
