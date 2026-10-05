"""The cataloguer's review queue (Desk → Review Queue): books whose records need a person's eye,
with the most important questions first.

Every night (and on *Scan now*) each published book is checked (core/review.py): no year or an
impossible one, no language or one that doesn't match the title's script, no author or one that
isn't a name, a title that is a file name or the identifier, no subjects, and possible duplicates.
Each question is an RD Review Flag. A flag closes itself when the record is corrected (on the
book's form, or right on the queue's page); "This is right" answers it for good.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.core import review as core

DT = "RD Review Flag"
EDITORS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
CHUNK = 2000
EDITABLE = ("title", "alt_title", "year", "language")


def _records(names: list[str]) -> list[dict]:
	"""The fields the checks read, for these books."""
	if not names:
		return []
	rows = frappe.get_all(
		"RD Item",
		filters={"name": ("in", names)},
		fields=["name as item_id", "title", "year", "date_raw", "language", "language_label"],
	)
	creators: dict[str, list[str]] = {}
	for c in frappe.get_all(
		"RD Item Creator",
		filters={"parent": ("in", names), "parenttype": "RD Item"},
		fields=["parent", "creator", "name_as_given", "idx"],
		order_by="idx asc",
	):
		creators.setdefault(c.parent, []).append(c.name_as_given or c.creator or "")
	with_subjects = set(
		frappe.get_all(
			"RD Item Subject", filters={"parent": ("in", names), "parenttype": "RD Item"}, pluck="parent"
		)
	)
	for r in rows:
		r["creators"] = creators.get(r["item_id"], [])
		r["subjects"] = [1] if r["item_id"] in with_subjects else []
	return rows


FIELDS = (
	"name",
	"item",
	"check",
	"label",
	"detail",
	"weight",
	"status",
	"noticed_on",
	"creation",
	"modified",
	"owner",
	"modified_by",
)


def _sync(item: str, found: list[dict], existing: dict[str, dict], new: list | None = None) -> None:
	"""Make the item's flags say what the checks found: new ones open, solved ones fixed,
	ignored ones left alone. New flags go into `new` (inserted together), or straight in."""
	now = now_datetime()
	seen = set()
	rows = [] if new is None else new
	for f in found:
		seen.add(f["code"])
		old = existing.get(f["code"])
		if old is None:
			rows.append(
				(
					frappe.generate_hash(length=12),
					item,
					f["code"],
					f["label"],
					f["detail"][:1000],
					f["weight"],
					"Open",
					now,
					now,
					now,
					"Administrator",
					"Administrator",
				)
			)
		elif old["status"] == "Fixed" or (old["status"] == "Open" and old["detail"] != f["detail"]):
			# back again after a fix (e.g. a re-ingest brought the old details back), or new detail
			frappe.db.set_value(
				DT,
				old["name"],
				{"status": "Open", "detail": f["detail"][:1000], "resolved_on": None, "resolved_by": None},
				update_modified=False,
			)
	for code, old in existing.items():
		if code not in seen and old["status"] == "Open":
			frappe.db.set_value(
				DT, old["name"], {"status": "Fixed", "resolved_on": now}, update_modified=False
			)
	if new is None and rows:
		frappe.db.bulk_insert(DT, FIELDS, rows)


def _existing(names: list[str]) -> dict[str, dict[str, dict]]:
	out: dict[str, dict[str, dict]] = {}
	for f in frappe.get_all(
		DT, filters={"item": ("in", names)}, fields=["name", "item", "check", "status", "detail"]
	):
		out.setdefault(f.item, {})[f.check] = {"name": f.name, "status": f.status, "detail": f.detail or ""}
	return out


def _duplicates() -> dict[str, list[str]]:
	"""Possible duplicates across the whole catalogue (title, first author, year)."""
	rows = frappe.db.sql(
		"""select i.name as item_id, i.title, i.year,
			(select coalesce(c.name_as_given, c.creator) from `tabRD Item Creator` c
			 where c.parent = i.name and c.parenttype = 'RD Item' order by c.idx limit 1) as first
		from `tabRD Item` i where i.published = 1""",
		as_dict=True,
	)
	return core.duplicates([{**r, "creators": [r.first or ""]} for r in rows])


def scan(names: list[str] | None = None) -> dict:
	"""Check these books (default: every published book) and bring their flags up to date."""
	dups = _duplicates()
	if names is None:
		names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="name")
	counts = {"books": 0, "flagged": 0}
	for start in range(0, len(names), CHUNK):
		chunk = names[start : start + CHUNK]
		existing = _existing(chunk)
		new: list = []
		for r in _records(chunk):
			found = core.check(r)
			if r["item_id"] in dups:
				found.append(core.flag("duplicate", ", ".join(dups[r["item_id"]][:10])))
			_sync(r["item_id"], found, existing.get(r["item_id"], {}), new)
			counts["books"] += 1
			counts["flagged"] += bool(found)
		if new:
			frappe.db.bulk_insert(DT, FIELDS, new)
		frappe.db.commit()
	return counts


def scan_item(item: str) -> None:
	"""One book, at once (after an edit); duplicates are left to the nightly scan."""
	existing = _existing([item]).get(item, {})
	for r in _records([item]):
		found = core.check(r)
		if "duplicate" in existing and existing["duplicate"]["status"] != "Fixed":
			found.append(core.flag("duplicate", existing["duplicate"]["detail"]))
		_sync(item, found, existing)


def nightly() -> None:
	scan()


def on_item_update(doc, method=None) -> None:
	"""RD Item saved by a person: its questions are answered (or asked) at once. Ingest saves
	many books; the nightly scan looks at those."""
	if doc.flags.from_ingest or frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	try:
		if frappe.db.exists(DT, {"item": doc.name}) or doc.published:
			scan_item(doc.name)
	except Exception:
		frappe.log_error(title=f"Research Desk: review check for {doc.name} failed")


def on_item_trash(doc, method=None) -> None:
	frappe.db.delete(DT, {"item": doc.name})


# ---- the page --------------------------------------------------------------------------------------


@frappe.whitelist()
def overview(check: str = "", q: str = "", start: int = 0) -> dict:
	"""Counts of open questions by check, and one page of books with theirs (most important first)."""
	frappe.only_for(EDITORS)
	counts = dict(
		frappe.db.sql(f"select `check`, count(*) from `tab{DT}` where status = 'Open' group by `check`")
	)
	cond, args = ["f.status = 'Open'"], {"start": cint(start)}
	if check:
		cond.append("f.`check` = %(check)s")
		args["check"] = check
	if q:
		cond.append("(i.title like %(q)s or i.name like %(q)s)")
		args["q"] = f"%{q}%"
	items = frappe.db.sql(
		f"""select f.item, min(f.weight) as w from `tab{DT}` f join `tabRD Item` i on i.name = f.item
		where {" and ".join(cond)} group by f.item order by w, f.item limit 25 offset %(start)s""",
		args,
		as_dict=True,
	)
	names = [r.item for r in items]
	books = {r["item_id"]: r for r in _records(names)}
	flags: dict[str, list] = {}
	for f in frappe.get_all(
		DT,
		filters={"item": ("in", names or [""]), "status": "Open"},
		fields=["name", "item", "check", "label", "detail", "weight"],
		order_by="weight asc",
	):
		if f.check == "duplicate":
			others = [x.strip() for x in (f.detail or "").split(",") if x.strip()]
			f.others = frappe.get_all(
				"RD Item",
				filters={"name": ("in", others or [""])},
				fields=["name", "title", "year", "published"],
			)
		flags.setdefault(f.item, []).append(f)
	rows = []
	for n in names:
		b = books.get(n)
		if b:
			rows.append({**b, "subjects": bool(b["subjects"]), "flags": flags.get(n, [])})
	languages = frappe.db.sql(
		"""select language, max(language_label) from `tabRD Item`
		where ifnull(language, '') != '' group by language order by count(*) desc limit 80"""
	)
	return {
		"counts": {code: counts.get(code, 0) for code in core.CHECKS},
		"labels": {code: _(label) for code, (label, _w) in core.CHECKS.items()},
		"rows": rows,
		"languages": [{"code": c, "label": lbl or c} for c, lbl in languages],
		"last_scan": frappe.db.sql(f"select max(noticed_on) from `tab{DT}`")[0][0],
	}


@frappe.whitelist(methods=["POST"])
def save(item: str, values) -> dict:
	"""Correct a book's title, other title, year or language right on the queue's page (kept
	through re-ingest, as an edit on the book's form is), then check it again."""
	frappe.only_for(EDITORS)
	values = frappe.parse_json(values) if isinstance(values, str) else values
	doc = frappe.get_doc("RD Item", item)
	for field in EDITABLE:
		if field not in values:
			continue
		value = values[field]
		if field == "year":
			value = cint(value) or None
		if field == "language":
			from sok_resdesk.core.normalize import normalize_language

			code, label = normalize_language(value)
			doc.language, doc.language_label = code or value, label or doc.language_label
			continue
		doc.set(field, (value or "").strip() if isinstance(value, str) else value)
	doc.save()
	scan_item(item)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def ignore(name: str) -> dict:
	"""This is right: the question is answered and not asked again."""
	frappe.only_for(EDITORS)
	frappe.db.set_value(
		DT, name, {"status": "Ignored", "resolved_by": frappe.session.user, "resolved_on": now_datetime()}
	)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def hide_duplicate(item: str) -> dict:
	"""A duplicate: take this copy off the portal (it stays in the Desk; publish it again any time)."""
	frappe.only_for(EDITORS)
	doc = frappe.get_doc("RD Item", item)
	doc.published = 0
	doc.save()
	frappe.db.set_value(
		DT,
		{"item": item, "status": "Open"},
		{"status": "Fixed", "resolved_by": frappe.session.user, "resolved_on": now_datetime()},
	)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def scan_now() -> dict:
	frappe.only_for(EDITORS)
	frappe.enqueue(
		"sok_resdesk.review.scan",
		queue="long",
		timeout=4 * 3600,
		job_id="resdesk-review-scan",
		deduplicate=True,
	)
	return {"queued": True}
