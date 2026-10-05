"""Giving back to the authorities (Desk → Authorities → Give back).

What the library has learned while matching its authors becomes edits for Wikidata: people's
names in the scripts of the library's books, and "author" links on the library's book items
(the ones its Wikidata Push Target created or found). A cataloguer looks at the list, then
either downloads it as QuickStatements (reviewed and run by a Wikidata editor under their own
account, the usual way) or sends it through the library's Wikidata Push Target. Nothing already
on Wikidata is changed or removed. Subjects with no Library of Congress heading are listed as a
spreadsheet for SACO proposals.

The plan is worked out in the background (it asks Wikidata what each person and book already
has) and kept for a day.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.core import authority as auth_core
from sok_resdesk.core import contribute as core
from sok_resdesk.core.push import LANG_CODE

EDITORS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
PLAN_KEY = "resdesk:contribute:plan"
SEND_KEY = "resdesk:contribute:last-send"
SUMMARY = "Names and authors from {0} (Research Desk)"


def _http_json(url: str) -> dict:
	from sok_resdesk.annotations import _http_json as get

	return get(url)


def _entities(qids: list[str]) -> dict[str, dict]:
	"""{Q: {labels: {lang: text}, aliases: {lang: [text]}, claims}} from Wikidata, 50 at a time."""
	out = {}
	qids = list(dict.fromkeys(q for q in qids if q))
	for start in range(0, len(qids), 50):
		data = _http_json(auth_core.entities_url(qids[start : start + 50]))
		for q, ent in (data.get("entities") or {}).items():
			if "missing" in ent:
				continue
			out[q] = {
				"labels": {k: v.get("value", "") for k, v in (ent.get("labels") or {}).items()},
				"aliases": {
					k: [a.get("value", "") for a in v] for k, v in (ent.get("aliases") or {}).items()
				},
				"claims": ent.get("claims") or {},
			}
	return out


def _people() -> dict[str, list[tuple[str, str]]]:
	"""{Q: [(a name the catalogue has for them, the Wikimedia language of that book)]}."""
	rows = frappe.db.sql(
		"""select c.wikidata_id, c.full_name, c.alt_name, ic.name_as_given, i.language
		from `tabRD Creator` c
		join `tabRD Item Creator` ic on ic.creator = c.name and ic.parenttype = 'RD Item'
		join `tabRD Item` i on i.name = ic.parent
		where ifnull(c.wikidata_id, '') != '' and c.match_status = 'Confirmed'""",
		as_dict=True,
	)
	out: dict[str, list] = {}
	for r in rows:
		lang = LANG_CODE.get(r.language or "", "")
		names = out.setdefault(r.wikidata_id, [])
		for n in (r.full_name, r.alt_name, r.name_as_given):
			if n and (n, lang) not in names:
				names.append((n, lang))
	return out


def _books_on_wikidata() -> list[dict]:
	"""The library's books that have an item on Wikidata, with their matched authors."""
	from sok_resdesk.catalogue import base_url

	rows = frappe.db.sql(
		"""select e.item, e.external_id from `tabRD External Record` e
		join `tabRD Push Target` t on t.name = e.target
		where t.target_type = 'Wikidata' and e.external_id like 'Q%%'""",
		as_dict=True,
	)
	out = []
	for r in rows:
		authors = frappe.db.sql(
			"""select c.wikidata_id as qid, coalesce(ic.name_as_given, ic.creator) as name, ic.idx as ordinal
			from `tabRD Item Creator` ic join `tabRD Creator` c on c.name = ic.creator
			where ic.parent = %s and ic.parenttype = 'RD Item' and c.match_status = 'Confirmed'
			and ifnull(c.wikidata_id, '') != '' order by ic.idx""",
			r.item,
			as_dict=True,
		)
		if authors:
			out.append(
				{
					"item": r.item,
					"qid": r.external_id,
					"authors": authors,
					"url": f"{base_url()}/library/item/{r.item}",
				}
			)
	return out


def build_plan() -> dict:
	"""Work out what to give back (a background job)."""
	people = _people()
	books = _books_on_wikidata()
	entities = _entities([*people, *[b["qid"] for b in books]])
	edits = []
	for q, names in people.items():
		if q in entities:
			edits += core.name_edits(q, entities[q], names)
	for b in books:
		if b["qid"] in entities:
			for e in core.author_edits(b["qid"], entities[b["qid"]]["claims"], b["authors"]):
				e["source_url"] = b["url"]
				e["item"] = b["item"]
				edits.append(e)
	plan = {
		"made_on": str(now_datetime()),
		"people": len(people),
		"books": len(books),
		"edits": edits,
	}
	frappe.cache.set_value(PLAN_KEY, plan, expires_in_sec=86400)
	return plan


@frappe.whitelist()
def plan() -> dict:
	"""Desk → Authorities → Give back: the edits worked out (or none yet), and the last send."""
	frappe.only_for(EDITORS)
	p = frappe.cache.get_value(PLAN_KEY) or {}
	edits = p.get("edits") or []
	counts = {k: sum(1 for e in edits if e["kind"] == k) for k in ("label", "alias", "author")}
	targets = frappe.get_all(
		"RD Push Target", filters={"target_type": "Wikidata", "enabled": 1}, fields=["name", "dry_run"]
	)
	return {
		"made_on": p.get("made_on"),
		"people": p.get("people", 0),
		"books": p.get("books", 0),
		"counts": counts,
		"edits": edits[:300],
		"targets": targets,
		"last_send": frappe.cache.get_value(SEND_KEY),
		"saco": _saco_count(),
	}


@frappe.whitelist(methods=["POST"])
def refresh() -> dict:
	frappe.only_for(EDITORS)
	frappe.enqueue(
		"sok_resdesk.contribute.build_plan",
		queue="long",
		timeout=3600,
		job_id="resdesk-contribute",
		deduplicate=True,
	)
	return {"queued": True}


@frappe.whitelist()
def quickstatements() -> None:
	"""The edits as QuickStatements, to review and run at quickstatements.toolforge.org."""
	frappe.only_for(EDITORS)
	p = frappe.cache.get_value(PLAN_KEY) or {}
	frappe.response["type"] = "download"
	frappe.response["filename"] = "research-desk-wikidata.qs.txt"
	frappe.response["filecontent"] = core.quickstatements(p.get("edits") or [])
	frappe.response["content_type"] = "text/plain; charset=utf-8"


@frappe.whitelist(methods=["POST"])
def send(target: str) -> dict:
	"""Send the edits through a Wikidata Push Target, in the background (a dry-run target only
	counts them)."""
	frappe.only_for(("System Manager", "ResDesk Manager"))
	t = frappe.get_doc("RD Push Target", target)
	if t.target_type != "Wikidata" or not t.enabled:
		frappe.throw(_("Choose an enabled Wikidata Push Target."))
	frappe.enqueue("sok_resdesk.contribute.run_send", queue="long", timeout=4 * 3600, target=target)
	return {"queued": True}


def run_send(target: str) -> dict:
	from sok_resdesk.catalogue import portal_title
	from sok_resdesk.outbound import _client as client_for

	p = frappe.cache.get_value(PLAN_KEY) or {}
	by_item: dict[str, list] = {}
	for e in p.get("edits") or []:
		by_item.setdefault(e["qid"], []).append(e)
	t = frappe.get_doc("RD Push Target", target)
	result = {
		"target": target,
		"dry_run": bool(t.dry_run),
		"items": 0,
		"edits": 0,
		"failed": 0,
		"when": str(now_datetime()),
	}
	if t.dry_run:
		result.update(items=len(by_item), edits=sum(len(v) for v in by_item.values()))
	else:
		client = client_for(t)
		client.login()
		summary = SUMMARY.format(portal_title())
		for qid, edits in by_item.items():
			try:
				client.edit(qid, core.wbeditentity_data(edits), summary)
				result["items"] += 1
				result["edits"] += len(edits)
			except Exception as e:
				result["failed"] += 1
				frappe.log_error(
					title=f"Research Desk: giving back to Wikidata ({qid}) failed", message=str(e)[:2000]
				)
		frappe.cache.delete_value(PLAN_KEY)  # what Wikidata has now changed: work it out again
	frappe.cache.set_value(SEND_KEY, result, expires_in_sec=30 * 86400)
	return result


def _saco_rows(limit: int = 5000) -> list[dict]:
	"""Subjects looked up with no LCSH heading found or chosen, the ones with most books first."""
	from urllib.parse import quote

	from sok_resdesk.catalogue import base_url

	rows = frappe.db.sql(
		"""select s.name as subject, s.match_status, count(i.name) as books from `tabRD Subject` s
		join `tabRD Item Subject` i on i.subject = s.name and i.parenttype = 'RD Item'
		where ifnull(s.lcsh_id, '') = '' and (s.match_status = 'No match' or s.matched_on is not null)
		group by s.name order by books desc limit %s""",
		cint(limit),
		as_dict=True,
	)
	for r in rows:
		r["titles"] = frappe.db.sql_list(
			"""select i.title from `tabRD Item Subject` s join `tabRD Item` i on i.name = s.parent
			where s.subject = %s and s.parenttype = 'RD Item' and i.published = 1 limit 3""",
			r["subject"],
		)
		r["url"] = f"{base_url()}/?subjects={quote(r['subject'])}"
		r["looked_at"] = "chosen none" if r["match_status"] == "No match" else "none found"
	return rows


def _saco_count() -> int:
	return frappe.db.sql(
		"""select count(*) from `tabRD Subject` s where ifnull(s.lcsh_id, '') = ''
		and (s.match_status = 'No match' or s.matched_on is not null)"""
	)[0][0]


@frappe.whitelist()
def saco() -> None:
	"""Subjects LCSH lacks, as a spreadsheet for SACO proposals."""
	frappe.only_for(EDITORS)
	frappe.response["type"] = "download"
	frappe.response["filename"] = "subjects-for-saco.csv"
	frappe.response["filecontent"] = "﻿" + core.saco_csv(_saco_rows())
	frappe.response["content_type"] = "text/csv; charset=utf-8"
