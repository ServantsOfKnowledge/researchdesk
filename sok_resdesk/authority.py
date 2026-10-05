"""Authority control (Desk → Authorities): the catalogue's authors matched to Wikidata people (and
through them VIAF), and its subjects to Library of Congress Subject Headings.

In the background (nightly when Settings → Authorities says so, or *Find matches* on the page)
each author not yet looked at is searched on Wikidata in every form of the name the catalogue
has; the people found are scored against the name and the years of the author's books
(core/authority.py) and kept as candidates. A cataloguer accepts one, chooses none, or searches
again. Accepting fills in the Wikidata and VIAF identifiers, the dates and a description, and
the books are sent to the search index again; two catalogue names for the same person can be
merged into one. Only near-certain matches are accepted without a person, and only when Settings
allow it.
"""

from __future__ import annotations

import json
import time

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import features
from sok_resdesk.core import authority as core
from sok_resdesk.core import wikidata

EDITORS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
KINDS = {"creator": "RD Creator", "subject": "RD Subject"}
KEEP = 5  # candidates kept for each name
PAUSE = 0.3  # seconds between requests to Wikidata / id.loc.gov: be polite


def _http_json(url: str) -> dict:
	from sok_resdesk.annotations import _http_json as get

	return get(url)


def _settings() -> dict:
	return frappe.db.get_singles_dict("RD Settings")


# ---- finding candidates ------------------------------------------------------------------------


def book_years(creator: str) -> list[int]:
	return [
		cint(y)
		for y in frappe.db.sql_list(
			"""select distinct i.year from `tabRD Item Creator` c join `tabRD Item` i on i.name = c.parent
			where c.creator = %s and c.parenttype = 'RD Item' and ifnull(i.year, 0) > 0""",
			creator,
		)
	]


def wikidata_candidates(names: list[str]) -> list[dict]:
	"""People on Wikidata for these forms of a name (each searched in its own script)."""
	ids: list[str] = []
	for name in names:
		clean = core.name_dates(name)[0]
		if len(clean) < 2:
			continue
		lang = wikidata.search_language(clean)
		try:
			hits = wikidata.parse_search(_http_json(core.search_url(clean, lang)))
		except Exception:
			continue
		ids += [h["id"] for h in hits if h["id"] not in ids]
		time.sleep(PAUSE)
	if not ids:
		return []
	return core.parse_people(_http_json(core.entities_url(ids[:20])))


def _slim(c: dict) -> dict:
	keep = ("id", "label", "description", "born", "died", "viaf", "human", "score", "reasons")
	return {k: c.get(k) for k in keep}


def match_creator(name: str, auto: bool | None = None) -> str:
	"""Look one author up; returns what happened: auto, proposed or none."""
	doc = frappe.db.get_value("RD Creator", name, ["full_name", "alt_name"], as_dict=True)
	names = [n for n in (doc.full_name, doc.alt_name) if n]
	ranked = core.rank(names, wikidata_candidates(names), book_years(name))[:KEEP]
	outcome = core.decide(ranked)
	if auto is None:
		auto = bool(cint(_settings().get("authority_auto_accept")))
	values = {"match_candidates": json.dumps([_slim(c) for c in ranked]), "matched_on": now_datetime()}
	if outcome == "auto" and auto:
		_accept_creator(name, ranked[0], by="Administrator")
		frappe.db.set_value("RD Creator", name, "match_candidates", values["match_candidates"])
		return "auto"
	values["match_status"] = "Proposed" if outcome in ("auto", "propose") else ""
	frappe.db.set_value("RD Creator", name, values, update_modified=False)
	return "proposed" if values["match_status"] else "none"


def match_subject(name: str) -> str:
	try:
		hits = core.parse_lcsh(_http_json(core.lcsh_url(name)))
	except Exception:
		hits = []
	ranked = sorted(
		({**h, "score": core.score_subject(name, h)} for h in hits), key=lambda h: h["score"], reverse=True
	)[:KEEP]
	status = "Proposed" if ranked and ranked[0]["score"] >= core.PROPOSE_AT else ""
	frappe.db.set_value(
		"RD Subject",
		name,
		{"match_candidates": json.dumps(ranked), "matched_on": now_datetime(), "match_status": status},
		update_modified=False,
	)
	return "proposed" if status else "none"


def waiting(kind: str, limit: int) -> list[str]:
	"""Names not looked at yet, the ones with most books first."""
	if kind == "creator":
		return frappe.db.sql_list(
			"""select c.name from `tabRD Creator` c
			left join `tabRD Item Creator` ic on ic.creator = c.name and ic.parenttype = 'RD Item'
			where ifnull(c.match_status, '') = '' and c.matched_on is null and ifnull(c.wikidata_id, '') = ''
			group by c.name order by count(ic.name) desc limit %s""",
			limit,
		)
	return frappe.db.sql_list(
		"""select s.name from `tabRD Subject` s
		left join `tabRD Item Subject` i on i.subject = s.name and i.parenttype = 'RD Item'
		where ifnull(s.match_status, '') = '' and s.matched_on is null and ifnull(s.lcsh_id, '') = ''
		group by s.name order by count(i.name) desc limit %s""",
		limit,
	)


def run(kind: str = "creator", limit: int = 200) -> dict:
	"""Find candidates for the next `limit` names (a background job)."""
	counts = {"auto": 0, "proposed": 0, "none": 0, "failed": 0}
	for name in waiting(kind, limit):
		try:
			counts[match_creator(name) if kind == "creator" else match_subject(name)] += 1
		except Exception as e:
			counts["failed"] += 1
			frappe.log_error(title=f"Research Desk: authority match for {name} failed", message=str(e)[:2000])
		frappe.db.commit()
		time.sleep(PAUSE)
	return counts


@features.scheduled("authorities")
def nightly() -> None:
	if cint(_settings().get("authority_nightly")):
		run("creator", 300)
		run("subject", 300)


# ---- deciding ----------------------------------------------------------------------------------


def _accept_creator(name: str, c: dict, by: str | None = None) -> None:
	values = {
		"wikidata_id": c["id"],
		"viaf_id": c.get("viaf") or "",
		"born": c.get("born") or 0,  # 0: not known (whole-number columns can't be empty)
		"died": c.get("died") or 0,
		"authority_description": (c.get("description") or "")[:255],
		"match_status": "Confirmed",
		"matched_by": by or frappe.session.user,
		"matched_on": now_datetime(),
	}
	if not frappe.db.get_value("RD Creator", name, "alt_name") and c.get("label") and c["label"] != name:
		values["alt_name"] = c["label"][:255]
	frappe.db.set_value("RD Creator", name, values)
	_reindex_books_of("creator", name)


def _reindex_books_of(kind: str, name: str) -> None:
	child, field = ("RD Item Creator", "creator") if kind == "creator" else ("RD Item Subject", "subject")
	items = frappe.get_all(child, filters={field: name, "parenttype": "RD Item"}, pluck="parent")
	if items:
		frappe.enqueue(
			"sok_resdesk.authority.reindex",
			queue="long",
			items=list(dict.fromkeys(items)),
			enqueue_after_commit=True,
		)


def reindex(items: list[str]) -> None:
	from sok_resdesk.search import reindex_item

	for item in items:
		try:
			reindex_item(item, with_pages=0)
		except Exception:
			pass


def _candidates(kind: str, name: str) -> list[dict]:
	raw = frappe.db.get_value(KINDS[kind], name, "match_candidates")
	try:
		return json.loads(raw) if raw else []
	except ValueError:
		return []


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def accept(kind: str, name: str, choice: str) -> dict:
	"""Accept a candidate (its Q-number, or LCSH id) for an author or subject."""
	frappe.only_for(EDITORS)
	if kind not in KINDS:
		frappe.throw(_("Unknown kind."))
	c = next((x for x in _candidates(kind, name) if x.get("id") == choice), None)
	if not c:
		frappe.throw(_("That candidate is not among those found for {0}. Search again first.").format(name))
	if kind == "subject":
		frappe.db.set_value(
			"RD Subject",
			name,
			{
				"lcsh_id": c["id"],
				"lcsh_label": c["label"][:255],
				"match_status": "Confirmed",
				"matched_by": frappe.session.user,
				"matched_on": now_datetime(),
			},
		)
		_reindex_books_of("subject", name)
		return {"ok": True}
	_accept_creator(name, c)
	same = frappe.get_all(
		"RD Creator",
		filters={"wikidata_id": c["id"], "name": ("!=", name)},
		fields=["name", "alt_name"],
	)
	# other catalogue names for the same person: offer to merge them
	return {"ok": True, "same_person": same}


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def reject(kind: str, name: str) -> dict:
	"""None of the candidates: the name stays as it is and is not proposed again."""
	frappe.only_for(EDITORS)
	frappe.db.set_value(
		KINDS[kind],
		name,
		{"match_status": "No match", "matched_by": frappe.session.user, "matched_on": now_datetime()},
	)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def undo(kind: str, name: str) -> dict:
	"""Back to undecided (keeps the candidates); a confirmed match loses its identifiers."""
	frappe.only_for(EDITORS)
	values = {"match_status": "Proposed" if _candidates(kind, name) else "", "matched_by": None}
	if kind == "creator":
		values.update({"wikidata_id": "", "viaf_id": "", "born": 0, "died": 0, "authority_description": ""})
	else:
		values.update({"lcsh_id": "", "lcsh_label": ""})
	frappe.db.set_value(KINDS[kind], name, values)
	_reindex_books_of(kind, name)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def search_again(kind: str, name: str, q: str = "") -> dict:
	"""Look again, with other words (e.g. the name as Wikidata or LCSH writes it) or a Q-number."""
	frappe.only_for(EDITORS)
	q = (q or "").strip()[:100]
	if kind == "subject":
		ranked = []
		try:
			hits = core.parse_lcsh(_http_json(core.lcsh_url(q or name)))
		except Exception:
			frappe.throw(_("id.loc.gov could not be reached just now. Try again later."))
		ranked = sorted(
			({**h, "score": core.score_subject(name, h)} for h in hits),
			key=lambda h: h["score"],
			reverse=True,
		)[:KEEP]
	else:
		doc = frappe.db.get_value("RD Creator", name, ["full_name", "alt_name"], as_dict=True)
		names = [n for n in (doc.full_name, doc.alt_name) if n]
		direct = wikidata.qid(q)
		try:
			people = (
				core.parse_people(_http_json(core.entities_url([direct])))
				if direct
				else wikidata_candidates([q] if q else names)
			)
		except Exception:
			frappe.throw(_("Wikidata could not be reached just now. Try again later."))
		ranked = [_slim(c) for c in core.rank(names, people, book_years(name))[:KEEP]]
	frappe.db.set_value(
		KINDS[kind],
		name,
		{
			"match_candidates": json.dumps(ranked),
			"matched_on": now_datetime(),
			"match_status": "Proposed" if ranked else frappe.db.get_value(KINDS[kind], name, "match_status"),
		},
		update_modified=False,
	)
	return {"candidates": ranked}


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def merge(name: str, into: str) -> dict:
	"""Two catalogue names for one person (the same Wikidata item): the books of `name` are
	listed under `into` (each keeps its name as printed), and `name` goes."""
	frappe.only_for(EDITORS)
	a = frappe.db.get_value("RD Creator", name, "wikidata_id")
	b = frappe.db.get_value("RD Creator", into, "wikidata_id")
	if not a or a != b:
		frappe.throw(_("Only names matched to the same Wikidata person can be merged."))
	items = frappe.get_all(
		"RD Item Creator", filters={"creator": name, "parenttype": "RD Item"}, pluck="parent"
	)
	frappe.rename_doc("RD Creator", name, into, merge=True, force=True)
	if items:
		frappe.enqueue(
			"sok_resdesk.authority.reindex",
			queue="long",
			items=list(dict.fromkeys(items)),
			enqueue_after_commit=True,
		)
	return {"ok": True, "books": len(set(items))}


@frappe.whitelist(methods=["POST"])
@features.needs("authorities")
def find(kind: str = "creator", limit: int = 200) -> dict:
	"""Desk → Authorities → Find matches: look up the next names in the background."""
	frappe.only_for(EDITORS)
	if kind not in KINDS:
		frappe.throw(_("Unknown kind."))
	limit = max(1, min(cint(limit) or 200, 2000))
	frappe.enqueue("sok_resdesk.authority.run", queue="long", timeout=6 * 3600, kind=kind, limit=limit)
	return {"queued": limit}


@frappe.whitelist()
def overview(kind: str = "creator", status: str = "Proposed", q: str = "", start: int = 0) -> dict:
	"""The page: counts by state, and one page of names with their candidates."""
	frappe.only_for(EDITORS)
	if kind not in KINDS:
		frappe.throw(_("Unknown kind."))
	dt = KINDS[kind]
	counts = dict(
		frappe.db.sql(
			f"select ifnull(match_status, ''), count(*) from `tab{dt}` group by ifnull(match_status, '')"
		)
	)
	waiting_count = frappe.db.count(dt, {"match_status": ("in", ("", None)), "matched_on": ("is", "not set")})
	filters: dict = {}
	if status == "Not looked at":
		filters = {"match_status": ("in", ("", None)), "matched_on": ("is", "not set")}
	elif status == "Nothing found":
		filters = {"match_status": ("in", ("", None)), "matched_on": ("is", "set")}
	elif status:
		filters = {"match_status": status}
	if q:
		filters["name"] = ("like", f"%{q}%")
	child, field = ("RD Item Creator", "creator") if kind == "creator" else ("RD Item Subject", "subject")
	extra = (
		["wikidata_id", "viaf_id", "born", "died", "authority_description", "alt_name"]
		if kind == "creator"
		else ["lcsh_id", "lcsh_label"]
	)
	rows = frappe.get_all(
		dt,
		filters=filters,
		fields=["name", "match_status", "match_candidates", "matched_by", *extra],
		order_by="modified desc",
		start=cint(start),
		limit=50,
	)
	for r in rows:
		r.candidates = json.loads(r.pop("match_candidates") or "[]")
		r.books = frappe.db.count(child, {field: r.name, "parenttype": "RD Item"})
	return {
		"counts": {
			"Proposed": counts.get("Proposed", 0),
			"Confirmed": counts.get("Confirmed", 0),
			"No match": counts.get("No match", 0),
			"Not looked at": waiting_count,
			"Nothing found": max(0, counts.get("", 0) - waiting_count),
		},
		"rows": rows,
	}


def creator_books(qid: str, limit: int = 200) -> list[dict]:
	"""The books of the authors matched to this Wikidata person (the entity page lists them)."""
	from sok_resdesk import access

	names = frappe.get_all("RD Creator", filters={"wikidata_id": qid}, pluck="name")
	if not names:
		return []
	return frappe.db.sql(
		f"""select distinct i.name as item_id, i.title, i.year from `tabRD Item` i
		join `tabRD Item Creator` c on c.parent = i.name and c.parenttype = 'RD Item'
		where c.creator in %(names)s and i.published = 1 and {access.sql_condition("i.visibility")}
		order by i.year is null, i.year, i.title limit %(limit)s""",
		{"names": names, "limit": limit},
		as_dict=True,
	)
