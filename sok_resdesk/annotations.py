"""Readers' notes on the pages of books (Page & text → select words, or mark a region of the page).

Who sees a note:
* **Private**: only its author;
* **Group**: the members of the author's research group (RD Research Group, made by staff);
* **Public**: everyone who may read the book, once a manager has approved it (until then, only
  its author and the managers);
* an **OCR error** report always reaches the managers too: it is the start of proofreading.

Notes are anchored in the page text by position and by quote (core/annotations.py), so a note
finds its words again after the text is corrected; a note whose words are gone shows as detached.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_fullname

from sok_resdesk import access
from sok_resdesk.core import annotations as core
from sok_resdesk.core import wikidata

DT = "RD Annotation"
MANAGERS = ("System Manager", "ResDesk Manager")
VISIBILITY = ("Private", "Group", "Public")
FIELDS = [
	"name",
	"item",
	"leaf",
	"page_label",
	"kind",
	"visibility",
	"research_group",
	"review_status",
	"body",
	"tags",
	"link",
	"entity",
	"entity_label",
	"entity_description",
	"exact",
	"prefix",
	"suffix",
	"pos_start",
	"pos_end",
	"region",
	"owner",
	"creation",
	"modified",
]


def _is_manager(user: str | None = None) -> bool:
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(MANAGERS))


def my_groups(user: str | None = None) -> list[dict]:
	user = user or frappe.session.user
	if user == "Guest":
		return []
	return frappe.db.sql(
		"""select g.name, g.group_name as title from `tabRD Research Group` g
		join `tabRD Research Group Member` m on m.parent = g.name and m.parenttype = 'RD Research Group'
		where m.user = %s order by g.group_name""",
		user,
		as_dict=True,
	)


def _visible_condition(user: str) -> tuple[str, dict]:
	"""SQL that keeps the notes `user` may see."""
	groups = [g.name for g in my_groups(user)]
	parts = ["(a.visibility = 'Public' and a.review_status = 'Approved')"]
	if user != "Guest":
		parts.append("a.owner = %(user)s")
	if groups:
		parts.append("(a.visibility = 'Group' and a.research_group in %(groups)s)")
	if _is_manager(user):
		parts.append("(a.visibility = 'Public' and a.review_status = 'Pending')")
		parts.append("a.kind = 'OCR error'")
	return "(" + " or ".join(parts) + ")", {"user": user, "groups": tuple(groups) or ("",)}


def _book(item_id: str) -> dict:
	row = frappe.db.get_value(
		"RD Item", item_id, ["name", "title", "published", "visibility", "has_page_text"], as_dict=True
	)
	if not row or not row.published or not access.can_find(row.visibility):
		frappe.throw(_("Item not found"), frappe.DoesNotExistError)
	return row


def _can_annotate(book: dict) -> bool:
	return frappe.session.user != "Guest" and access.can_read(book.visibility)


def _page_text(item_id: str, leaf: int) -> str | None:
	from sok_resdesk.ingest import fetch_pages

	try:
		for p in fetch_pages(item_id):
			if p["leaf"] == leaf:
				return p.get("text") or ""
	except Exception:
		return None
	return ""


def _present(row: dict, text: str | None, user: str) -> dict:
	"""A note for the reader: anchored in the page text as it is now."""
	out = {k: row.get(k) for k in FIELDS if k not in ("owner",)}
	out["mine"] = row.owner == user
	out["author"] = "" if out["mine"] else get_fullname(row.owner)
	out["tags"] = core.split_tags(row.tags)
	out["creation"] = str(row.creation)[:19]
	out["modified"] = str(row.modified)[:19]
	out["detached"] = False
	if row.exact and text is not None:
		where = core.anchor(text, row.pos_start, row.pos_end, row.exact, row.prefix or "", row.suffix or "")
		if where:
			out["pos_start"], out["pos_end"] = where
		else:
			out["detached"] = True
	return out


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=300, seconds=60)
def page_notes(item_id: str, leaf: int = 0) -> dict:
	"""The notes on one page this reader may see, and what they may do."""
	book = _book(item_id)
	user = frappe.session.user
	leaf = cint(leaf)
	readable = access.can_read(book.visibility)
	me = {
		"logged_in": user != "Guest",
		"can_annotate": _can_annotate(book),
		"groups": my_groups(user) if user != "Guest" else [],
		"manager": _is_manager(user),
	}
	if not readable:
		return {"notes": [], "me": me}
	cond, params = _visible_condition(user)
	rows = frappe.db.sql(
		f"select {', '.join('a.' + f for f in FIELDS)} from `tab{DT}` a "
		f"where a.item = %(item)s and a.leaf = %(leaf)s and {cond} order by a.pos_start, a.creation",
		{**params, "item": item_id, "leaf": leaf},
		as_dict=True,
	)
	text = _page_text(item_id, leaf) if any(r.exact for r in rows) else None
	return {"notes": [_present(r, text, user) for r in rows], "me": me}


def _clean(values: dict, book: dict, existing=None) -> dict:
	kind = values.get("kind") or (existing.kind if existing else "Comment")
	if kind not in core.MOTIVATIONS:
		frappe.throw(_("Unknown kind of note: {0}").format(kind))
	visibility = values.get("visibility") or (existing.visibility if existing else "Private")
	if visibility not in VISIBILITY:
		frappe.throw(_("Choose who can see it: Private, Group or Public."))
	group = (
		values.get("research_group")
		if "research_group" in values
		else (existing.research_group if existing else None)
	)
	if visibility == "Group":
		if not group or group not in {g.name for g in my_groups()}:
			frappe.throw(_("Choose one of your research groups."))
	else:
		group = None
	link = (values.get("link") if "link" in values else (existing.link if existing else "")) or ""
	link = link.strip()
	if link and not link.startswith(("https://", "http://")):
		frappe.throw(_("A link must start with https://"))
	entity_in = values.get("entity") if "entity" in values else None
	if entity_in is None and kind == "Link" and wikidata.qid(link):
		entity_in = link  # a link to a Wikidata page says what the passage is about
	if entity_in is None:
		entity = existing.entity if existing else ""
		names = (existing.entity_label, existing.entity_description) if existing else ("", "")
	else:
		entity = wikidata.qid(entity_in) or ""
		if entity_in and not entity:
			frappe.throw(_("Choose a Wikidata item (a Q-number such as Q2724213)."))
		names = (
			(existing.entity_label, existing.entity_description)
			if existing and existing.entity == entity
			else ("", "")
		)
		if entity and not names[0]:
			found = describe([entity]).get(entity) or {}
			names = (found.get("label") or "", found.get("description") or "")
	out = {
		"entity": entity,
		"entity_label": (names[0] or entity)[:140] if entity else "",
		"entity_description": (names[1] or "")[:140] if entity else "",
		"kind": kind,
		"visibility": visibility,
		"research_group": group,
		"body": (values.get("body") if "body" in values else (existing.body if existing else "")) or "",
		"tags": ", ".join(
			core.split_tags(values.get("tags") if "tags" in values else (existing.tags if existing else ""))
		)[:500],
		"link": link[:500],
	}
	out["body"] = out["body"][:5000]
	was_public = existing and existing.visibility == "Public"
	if visibility == "Public" and not was_public:
		out["review_status"] = "Approved" if _is_manager() else "Pending"
	elif visibility != "Public":
		out["review_status"] = ""
	if kind in ("Comment", "Question") and not out["body"].strip():
		frappe.throw(_("Write the note first."))
	if kind == "Tag" and not out["tags"]:
		frappe.throw(_("Give at least one tag."))
	if kind == "Link" and not out["link"]:
		frappe.throw(_("Give the link."))
	return out


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def add(
	item_id: str,
	leaf: int,
	kind: str = "Comment",
	body: str = "",
	tags: str = "",
	link: str = "",
	start: int | None = None,
	end: int | None = None,
	region: str = "",
	visibility: str = "Private",
	research_group: str = "",
	page_label: str = "",
	entity: str = "",
) -> dict:
	"""A new note on a passage (start, end in the page text) or a region (x,y,w,h in percent)."""
	book = _book(item_id)
	if not _can_annotate(book):
		frappe.throw(_("Log in to add notes."), frappe.PermissionError)
	leaf = cint(leaf)
	values = _clean(
		{
			"kind": kind,
			"body": body,
			"tags": tags,
			"link": link,
			"visibility": visibility,
			"research_group": research_group,
			"entity": entity,
		},
		book,
	)
	target: dict = {}
	if region:
		parts = [float(x) for x in str(region).replace("xywh=percent:", "").split(",")[:4]]
		if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
			frappe.throw(_("Mark a region of the page first."))
		target["region"] = core.region(*parts)
	else:
		text = _page_text(item_id, leaf)
		start, end = cint(start), cint(end)
		if not text or not (0 <= start < end <= len(text)):
			frappe.throw(_("Select some words of the page text first."))
		q = core.quote_selector(text, start, end)
		target = {
			"exact": q["exact"][:2000],
			"prefix": q["prefix"],
			"suffix": q["suffix"],
			"pos_start": start,
			"pos_end": end,
		}
	doc = frappe.get_doc(
		{
			"doctype": DT,
			"item": item_id,
			"leaf": leaf,
			"page_label": (page_label or "")[:20],
			**values,
			**target,
		}
	).insert(ignore_permissions=True)
	return _present(frappe.db.get_value(DT, doc.name, FIELDS, as_dict=True), None, frappe.session.user)


def _own(name: str):
	doc = frappe.get_doc(DT, name)
	if doc.owner != frappe.session.user and not _is_manager():
		frappe.throw(_("Only its author can change this note."), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def edit(name: str, **values) -> dict:
	doc = _own(name)
	book = _book(doc.item)
	values = {
		k: v
		for k, v in values.items()
		if k in ("kind", "body", "tags", "link", "visibility", "research_group", "entity")
	}
	doc.update(_clean(values, book, existing=doc))
	doc.save(ignore_permissions=True)
	return _present(frappe.db.get_value(DT, doc.name, FIELDS, as_dict=True), None, frappe.session.user)


@frappe.whitelist(methods=["POST"])
def remove(name: str) -> None:
	_own(name)
	frappe.delete_doc(DT, name, ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def review(name: str, decision: str) -> None:
	"""Managers: approve or reject a public note."""
	frappe.only_for(MANAGERS)
	if decision not in ("Approved", "Rejected"):
		frappe.throw(_("Approve or reject."))
	frappe.db.set_value(DT, name, "review_status", decision)
	book_notes_changed(frappe.db.get_value(DT, name, "item"))


# -- notes as data: Wikidata items, tags, and the books they find -----------------------------------


def _http_json(url: str) -> dict:
	import requests

	resp = requests.get(
		url,
		timeout=8,
		headers={"User-Agent": "SOK-ResearchDesk (+https://github.com/ServantsOfKnowledge/researchdesk)"},
	)
	resp.raise_for_status()
	return resp.json()


def describe(ids: list[str], language: str = "en") -> dict[str, dict]:
	"""{Q: {label, description}} from Wikidata (cached a week); {} when it can't be reached."""
	ids = [q for q in dict.fromkeys(wikidata.qid(i) for i in ids) if q]
	out, missing = {}, []
	cache = frappe.cache()
	for q in ids:
		hit = cache.get_value(f"resdesk:wikidata:{language}:{q}")
		if hit:
			out[q] = hit
		else:
			missing.append(q)
	if missing:
		try:
			found = wikidata.parse_entities(_http_json(wikidata.entities_url(missing, language)), language)
		except Exception:
			found = {}
		for q, v in found.items():
			cache.set_value(f"resdesk:wikidata:{language}:{q}", v, expires_in_sec=7 * 86400)
			out[q] = v
	return out


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def wikidata_search(q: str, language: str = "") -> list[dict]:
	"""Wikidata items matching what a reader typed, for "About" on a note (logged-in readers)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to add notes."), frappe.PermissionError)
	q = (q or "").strip()[:100]
	if len(q) < 2:
		return []
	direct = wikidata.qid(q)
	if direct:
		found = describe([direct])
		return [{"id": direct, **found.get(direct, {"label": direct, "description": ""})}]
	lang = wikidata.search_language(q, (language or "en")[:8])
	key = f"resdesk:wikidata-search:{lang}:{q.lower()}"
	hits = frappe.cache().get_value(key)
	if hits is None:
		try:
			hits = wikidata.parse_search(_http_json(wikidata.search_url(q, lang)))
		except Exception:
			frappe.throw(
				_("Wikidata could not be reached just now. Try again, or paste the item's Q-number.")
			)
		frappe.cache().set_value(key, hits, expires_in_sec=86400)
	return hits


def public_labels(item_id: str) -> dict:
	"""The tags and Wikidata items of a book's public notes (approved): searched with the book."""
	rows = frappe.db.sql(
		f"""select tags, entity, entity_label from `tab{DT}`
		where item = %s and visibility = 'Public' and review_status = 'Approved'""",
		item_id,
		as_dict=True,
	)
	tags, entities, labels = [], [], []
	for r in rows:
		tags.extend(core.split_tags(r.tags))
		if r.entity:
			entities.append(r.entity)
			if r.entity_label:
				labels.append(r.entity_label)
	return {
		"note_tags": list(dict.fromkeys(tags))[:200],
		"note_entities": list(dict.fromkeys(entities))[:200],
		"note_entity_names": list(dict.fromkeys(labels))[:200],
	}


def _counts_publicly(doc) -> bool:
	return bool(doc) and doc.visibility == "Public" and doc.review_status == "Approved"


def on_change(doc, method=None) -> None:
	"""A public note added, changed or gone: the book's search entry follows (tags, Wikidata)."""
	before = doc.get_doc_before_save() if method == "on_update" else None
	if _counts_publicly(doc) or _counts_publicly(before):
		book_notes_changed(doc.item)


def book_notes_changed(item_id: str | None) -> None:
	if not item_id:
		return
	frappe.enqueue(
		"sok_resdesk.search.update_item_fields",
		queue="short",
		names=[item_id],
		enqueue_after_commit=True,
		job_id=f"resdesk-notes-{item_id}",
		deduplicate=True,
	)


def _public_notes(where: str, params: dict, limit: int = 500) -> list[dict]:
	"""Approved public notes matching `where`, on books this visitor may read, with page links."""
	rows = frappe.db.sql(
		f"""select {", ".join("a." + f for f in FIELDS)}, i.title as book_title, i.persistent_id,
		i.visibility as book_visibility, i.year, i.language_label
		from `tab{DT}` a join `tabRD Item` i on i.name = a.item
		where i.published = 1 and a.visibility = 'Public' and a.review_status = 'Approved' and {where}
		order by i.title, a.item, a.leaf, a.pos_start limit %(limit)s""",
		{**params, "limit": limit},
		as_dict=True,
	)
	rows = [r for r in rows if access.can_read(r.book_visibility)]
	return _with_citation(rows)


def notes_about(entity: str) -> list[dict]:
	"""Public notes about a Wikidata item (the portal's /library/entity/Q… page)."""
	q = wikidata.qid(entity)
	return _public_notes("a.entity = %(q)s", {"q": q}) if q else []


def notes_tagged(tag: str) -> list[dict]:
	"""Public notes with a tag (the portal's /library/tag/… page)."""
	tag = (tag or "").strip()
	if not tag:
		return []
	notes = _public_notes("a.tags like %(like)s", {"like": f"%{tag}%"})
	return [n for n in notes if tag.lower() in [t.lower() for t in n.get("tags") or []]]


def by_book(notes: list[dict]) -> list[dict]:
	"""Notes grouped by book, in order: [{item, title, citation, notes}]."""
	out: list[dict] = []
	for n in notes:
		if not out or out[-1]["item"] != n["item"]:
			out.append(
				{
					"item": n["item"],
					"title": n.get("book_title"),
					"citation": n.get("book_citation"),
					"notes": [],
				}
			)
		out[-1]["notes"].append(n)
	return out


# -- my notes, exports and the W3C collection ---------------------------------------------------------


def _notes_for(
	user: str,
	q: str = "",
	kind: str = "",
	item: str = "",
	mine_only: int = 0,
	limit: int = 200,
	start: int = 0,
):
	cond, params = _visible_condition(user)
	where = [cond]
	if cint(mine_only):
		where.append("a.owner = %(user)s")
	if kind:
		where.append("a.kind = %(kind)s")
	if item:
		where.append("a.item = %(item)s")
	if q:
		where.append(
			"(a.body like %(q)s or a.exact like %(q)s or a.tags like %(q)s or a.entity_label like %(q)s"
			" or a.entity = %(q_exact)s or i.title like %(q)s)"
		)
	return frappe.db.sql(
		f"""select {", ".join("a." + f for f in FIELDS)}, i.title as book_title, i.persistent_id
		from `tab{DT}` a join `tabRD Item` i on i.name = a.item
		where i.published = 1 and {" and ".join(where)}
		order by i.title, a.item, a.leaf, a.pos_start, a.creation limit %(limit)s offset %(start)s""",
		{
			**params,
			"q": f"%{q}%",
			"q_exact": q.strip().upper(),
			"kind": kind,
			"item": item,
			"limit": min(cint(limit) or 200, 2000),
			"start": cint(start),
		},
		as_dict=True,
	)


def _with_citation(rows) -> list[dict]:
	from sok_resdesk.catalogue import base_url, get_record
	from sok_resdesk.core import citations

	books: dict[str, dict | None] = {}
	out = []
	for r in rows:
		if r.item not in books:
			books[r.item] = get_record(r.item)
		record = books[r.item]
		note = _present(r, None, frappe.session.user)
		note.update({"book_title": r.book_title, "exact": r.exact, "region": r.region})
		if record:
			cited = citations.with_page(record, cint(r.leaf), r.page_label or "", base_url())
			note.update(
				{
					"page": citations.page_phrase(cited),
					"url": cited["page_url"],
					"book_citation": citations.to_apa(record, base_url()),
				}
			)
		out.append(note)
	return out


@frappe.whitelist(methods=["GET"])
def mine(
	q: str = "", kind: str = "", item: str = "", mine_only: int = 0, limit: int = 200, start: int = 0
) -> dict:
	"""My notes, and my groups' (the My notes page)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to see your notes."), frappe.PermissionError)
	rows = _notes_for(frappe.session.user, q, kind, item, mine_only, limit, start)
	return {"notes": _with_citation(rows), "groups": my_groups()}


@frappe.whitelist(methods=["GET"])
def export(format: str = "markdown", q: str = "", kind: str = "", item: str = "", mine_only: int = 0):
	"""My notes (and my groups') as Markdown, a spreadsheet (CSV) or W3C Web Annotations (JSON-LD)."""
	from sok_resdesk.api import _text_response

	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to export your notes."), frappe.PermissionError)
	notes = _with_citation(_notes_for(frappe.session.user, q, kind, item, mine_only, limit=2000))
	if format == "csv":
		return _text_response(core.to_csv(notes), "text/csv", "my-notes.csv")
	if format == "jsonld":
		items = [_w3c(n) for n in notes]
		body = frappe.as_json(core.page_collection(items, _url("export") + "?format=jsonld"))
		return _text_response(body, "application/ld+json", "my-notes.jsonld")
	return _text_response(core.to_markdown(notes), "text/markdown", "my-notes.md")


def _url(method: str) -> str:
	from sok_resdesk.catalogue import base_url

	return f"{base_url()}/api/method/sok_resdesk.annotations.{method}"


def annotation_iri(item_id: str, name: str) -> str:
	"""A note's address in the Web Annotation Protocol (annotation_protocol.py): GET, PUT, DELETE."""
	from sok_resdesk.annotation_protocol import annotation_iri as iri

	return iri(item_id, name)


def _w3c(note: dict) -> dict:
	return core.to_w3c(
		{
			**note,
			"id": annotation_iri(note["item"], note["name"]),
			"start": note.get("pos_start"),
			"end": note.get("pos_end"),
			"creator": note.get("author") or "",
		},
		note.get("url") or "",
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def collection(item_id: str, leaf: int | None = None):
	"""The book's public notes (approved) as a W3C AnnotationPage, for other annotation tools."""
	from sok_resdesk.api import _text_response

	book = _book(item_id)
	rows = []
	if access.can_read(book.visibility):
		rows = frappe.db.sql(
			f"""select {", ".join("a." + f for f in FIELDS)}, i.title as book_title, i.persistent_id
			from `tab{DT}` a join `tabRD Item` i on i.name = a.item
			where a.item = %(item)s and a.visibility = 'Public' and a.review_status = 'Approved'
			{"and a.leaf = %(leaf)s" if leaf is not None else ""} order by a.leaf, a.pos_start""",
			{"item": item_id, "leaf": cint(leaf)},
			as_dict=True,
		)
	items = [_w3c(n) for n in _with_citation(rows)]
	body = frappe.as_json(core.page_collection(items, f"{_url('collection')}?item_id={item_id}"))
	return _text_response(body, "application/ld+json")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get(name: str):
	"""One note as a W3C Web Annotation, if this visitor may see it."""
	from sok_resdesk.api import _text_response

	row = frappe.db.get_value(DT, name, ["item"], as_dict=True)
	if not row:
		raise frappe.DoesNotExistError
	cond, params = _visible_condition(frappe.session.user)
	rows = frappe.db.sql(
		f"""select {", ".join("a." + f for f in FIELDS)}, i.title as book_title, i.persistent_id
		from `tab{DT}` a join `tabRD Item` i on i.name = a.item where a.name = %(name)s and {cond}""",
		{**params, "name": name},
		as_dict=True,
	)
	if not rows or not access.can_read(frappe.db.get_value("RD Item", row.item, "visibility")):
		raise frappe.DoesNotExistError
	return _text_response(frappe.as_json(_w3c(_with_citation(rows)[0])), "application/ld+json")
