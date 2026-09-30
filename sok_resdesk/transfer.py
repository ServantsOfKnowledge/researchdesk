"""Metadata export (many formats) and spreadsheet import (bulk editing).

Formats live in core/metaio.py, core/marc.py and core/citations.py; this module chooses the
books, runs large jobs in the background, stores the file and applies imported changes.
"""

from __future__ import annotations

import io
import json
import zipfile

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import base_url, item_to_record
from sok_resdesk.core import citations, marc, metaio
from sok_resdesk.holding import hold_when_paused

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
BACKGROUND_OVER = 500

# format -> (file extension, content type)
FORMATS = {
	"Spreadsheet (CSV)": ("csv", "text/csv"),
	"Spreadsheet (Excel)": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
	"JSON (everything)": ("json", "application/json"),
	"JSON Lines": ("jsonl", "application/x-ndjson"),
	"Dublin Core XML": ("xml", "application/xml"),
	"MODS XML": ("mods.xml", "application/mods+xml"),
	"MARCXML (Koha)": ("marc.xml", "application/marcxml+xml"),
	"JSON-LD (schema.org)": ("jsonld", "application/ld+json"),
	"CSL-JSON": ("csl.json", "application/vnd.citationstyles.csl+json"),
	"BibTeX": ("bib", "application/x-bibtex"),
	"RIS": ("ris", "application/x-research-info-systems"),
	"Internet Archive bulk-upload CSV": ("ia.csv", "text/csv"),
	"Internet Archive meta.xml files (zip)": ("zip", "application/zip"),
}


# -- choosing books ------------------------------------------------------------------------------

def select_for_export(doc) -> list[str]:
	from sok_resdesk.access import select_items

	scope = doc.scope
	if scope == "Collection":
		names = frappe.db.sql_list(
			"select distinct parent from `tabRD Item Collection` where collection=%s and parenttype='RD Item'",
			doc.collection,
		)
	elif scope == "Ingest Profile":
		names = select_items(profile=doc.profile)
	elif scope == "Source Collection":
		names = select_items(collection=doc.source_collection)
	elif scope == "Search":
		names = select_items(search={"q": doc.search_query or "", "mode": "books", "filters": {}})
	elif scope in ("Filters", "Selected Books"):
		spec = json.loads(doc.filters_json or "[]")
		names = select_items(names=spec) if scope == "Selected Books" else select_items(filters=spec or None, everything=not spec)
	else:
		names = select_items(everything=True)
	if not cint(doc.include_unpublished) and names:
		published = set()
		for i in range(0, len(names), 1000):
			published.update(frappe.get_all("RD Item", filters={"name": ("in", names[i:i + 1000]), "published": 1}, pluck="name"))
		names = [n for n in names if n in published]
	return names


def _records(names: list[str]):
	for name in names:
		yield item_to_record(frappe.get_doc("RD Item", name))


# -- building files ------------------------------------------------------------------------------

def build(fmt: str, names: list[str], stem: str = "export") -> tuple[str, bytes]:
	root = base_url()
	records = list(_records(names))
	ext = FORMATS[fmt][0]
	name = f"{stem}.{ext}"
	if fmt == "Spreadsheet (CSV)":
		return name, metaio.rows_to_csv([metaio.record_to_row(r, root) for r in records]).encode()
	if fmt == "Spreadsheet (Excel)":
		from frappe.utils.xlsxutils import make_xlsx

		header = [c for c, _k, _e in metaio.COLUMNS]
		rows = [header] + [[metaio.record_to_row(r, root)[c] for c in header] for r in records]
		return name, make_xlsx(rows, "Books").getvalue()
	if fmt == "JSON (everything)":
		return name, json.dumps([metaio.json_record(r, root) for r in records], ensure_ascii=False, indent=1).encode()
	if fmt == "JSON Lines":
		return name, "".join(json.dumps(metaio.json_record(r, root), ensure_ascii=False) + "\n" for r in records).encode()
	if fmt == "Dublin Core XML":
		return name, metaio.dublin_core_collection(records, root).encode()
	if fmt == "MODS XML":
		return name, metaio.mods_collection(records, root).encode()
	if fmt == "MARCXML (Koha)":
		return name, marc.to_marcxml_collection(records, root).encode()
	if fmt == "JSON-LD (schema.org)":
		return name, metaio.jsonld_graph(records, root).encode()
	if fmt == "CSL-JSON":
		return name, json.dumps([citations.to_csl(r, root) for r in records], ensure_ascii=False, indent=1).encode()
	if fmt == "BibTeX":
		return name, "\n".join(citations.to_bibtex(r, root) for r in records).encode()
	if fmt == "RIS":
		return name, "".join(citations.to_ris(r, root) for r in records).encode()
	if fmt == "Internet Archive bulk-upload CSV":
		return name, metaio.ia_bulk_csv(records).encode()
	if fmt == "Internet Archive meta.xml files (zip)":
		buf = io.BytesIO()
		with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
			for r in records:
				z.writestr(f"{r['item_id']}/{r['item_id']}_meta.xml", metaio.meta_xml(r))
		return name, buf.getvalue()
	frappe.throw(_("Unknown format {0}").format(fmt))


# -- export runs ---------------------------------------------------------------------------------

def _set(name: str, **values):
	frappe.db.set_value("RD Export", name, values, update_modified=False)
	frappe.db.commit()


def start_export(name: str) -> None:
	doc = frappe.get_doc("RD Export", name)
	names = select_for_export(doc)
	if len(names) > BACKGROUND_OVER:
		_set(name, status="Queued", item_count=len(names))
		frappe.enqueue("sok_resdesk.transfer.run_export", queue="long", timeout=6 * 3600, name=name,
					   enqueue_after_commit=True, job_id=f"resdesk-export-{name}")
	else:
		run_export(name, names)


@hold_when_paused("long")
def run_export(name: str, names: list[str] | None = None) -> None:
	doc = frappe.get_doc("RD Export", name)
	_set(name, status="Running")
	try:
		names = names if names is not None else select_for_export(doc)
		stem = frappe.scrub(doc.collection or doc.profile or doc.source_collection or doc.scope or "export")
		fname, content = build(doc.export_format, names, f"{stem}-{name.lower()}")
		f = frappe.get_doc({
			"doctype": "File", "file_name": fname, "attached_to_doctype": "RD Export", "attached_to_name": name,
			"is_private": 1, "content": content,
		}).insert(ignore_permissions=True)
		_set(name, status="Done", item_count=len(names), file_url=f.file_url, finished_on=now_datetime(),
			 log=f"{len(names)} books, {len(content):,} bytes")
	except Exception:
		frappe.db.rollback()
		_set(name, status="Failed", finished_on=now_datetime(), log=frappe.get_traceback()[-4000:])
		frappe.log_error("Research Desk: export failed")


@frappe.whitelist()
def rerun_export(name: str) -> None:
	frappe.only_for(STAFF)
	_set(name, status="Draft", file_url="", item_count=0, log="")
	start_export(name)


@frappe.whitelist()
def quick_export(export_format: str, search=None, collection=None, filters=None):
	"""Download straight away (for small selections, e.g. the portal staff bar). Staff only."""
	frappe.only_for(STAFF)
	from sok_resdesk.access import select_items

	if collection:
		names = frappe.db.sql_list("select distinct parent from `tabRD Item Collection` where collection=%s", collection)
	else:
		names = select_items(search=search, filters=filters, everything=not (search or filters))
	if len(names) > 2000:
		frappe.throw(_("{0} books is a lot for a direct download: use Desk → Research Desk → Exports.").format(len(names)))
	fname, content = build(export_format, names, "books")
	frappe.local.response.filename = fname
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


# -- spreadsheet import --------------------------------------------------------------------------

def _read_rows(file_url: str) -> list[dict]:
	f = frappe.get_doc("File", {"file_url": file_url})
	content = f.get_content()
	if file_url.lower().endswith((".xlsx", ".xls")):
		from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

		table = read_xlsx_file_from_attached_file(fcontent=content)
		if not table:
			return []
		header = [str(h or "").strip() for h in table[0]]
		return [{header[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(r) if i < len(header)}
				for r in table[1:] if any(v not in (None, "") for v in r)]
	return metaio.csv_to_rows(content)


def _collection_names(values: list[str]) -> tuple[list[str], list[str]]:
	"""Map collection names or titles to collection ids; unknown ones are created."""
	out, created = [], []
	for v in values:
		name = frappe.db.get_value("RD Collection", v, "name") or frappe.db.get_value("RD Collection", {"title": v}, "name")
		if not name:
			name = frappe.get_doc({"doctype": "RD Collection", "title": v}).insert().name
			created.append(v)
		out.append(name)
	return out, created


def plan_import(name: str) -> dict:
	doc = frappe.get_doc("RD Metadata Import", name)
	rows = _read_rows(doc.import_file)
	if rows and "item_id" not in rows[0]:
		frappe.throw(_("The spreadsheet needs an item_id column."))
	plan, lines, problems, new = [], [], 0, 0
	for n, row in enumerate(rows, 2):
		item_id = (row.get("item_id") or "").strip()
		if not item_id:
			continue
		if frappe.db.exists("RD Item", item_id):
			current = item_to_record(frappe.get_doc("RD Item", item_id))
			current["published"] = bool(frappe.db.get_value("RD Item", item_id, "published"))
			changes, issues = metaio.row_changes(row, current)
		elif cint(doc.create_missing):
			if not row.get("title"):
				issues, changes = ["no title for a new record"], {}
			else:
				changes, issues = metaio.row_changes(row, {})
				changes["__new__"] = True
				new += 1
		else:
			lines.append(f"row {n}: {item_id} is not in the catalogue (skipped)")
			continue
		for issue in issues:
			lines.append(f"row {n}: {item_id}: {issue}")
		problems += len(issues)
		if changes:
			plan.append((item_id, changes))
			summary = ", ".join(k for k in changes if k != "__new__")
			lines.append(f"{'NEW ' if changes.get('__new__') else ''}{item_id}: {summary}")
	return {"rows": len(rows), "plan": plan, "lines": lines, "problems": problems, "new": new}


@frappe.whitelist()
def preview_import(name: str) -> dict:
	frappe.only_for(STAFF)
	p = plan_import(name)
	frappe.db.set_value("RD Metadata Import", name, {
		"status": "Previewed", "rows": p["rows"], "changed": len(p["plan"]), "created": p["new"],
		"problems": p["problems"], "preview": "\n".join(p["lines"][:3000]) or _("Nothing to change."),
	})
	return {"message": _("{0} rows read: {1} books would change ({2} new), {3} problems.").format(
		p["rows"], len(p["plan"]), p["new"], p["problems"])}


@frappe.whitelist()
def apply_import(name: str) -> dict:
	frappe.only_for(STAFF)
	p = plan_import(name)
	if len(p["plan"]) > 200:
		frappe.db.set_value("RD Metadata Import", name, "status", "Queued")
		frappe.enqueue("sok_resdesk.transfer.apply_plan", queue="long", timeout=6 * 3600, name=name,
					   enqueue_after_commit=True, job_id=f"resdesk-import-{name}")
		return {"message": _("Applying changes to {0} books in the background.").format(len(p["plan"]))}
	return apply_plan(name, p)


@hold_when_paused("long")
def apply_plan(name: str, p: dict | None = None) -> dict:
	from sok_resdesk.catalogue import _ensure_creator, _ensure_subject
	from sok_resdesk.search import SearchError, update_item_fields

	frappe.db.set_value("RD Metadata Import", name, "status", "Applying")
	frappe.db.commit()
	p = p or plan_import(name)
	done, log = [], []
	for item_id, changes in p["plan"]:
		try:
			changes = dict(changes)
			is_new = changes.pop("__new__", False)
			doc = frappe.new_doc("RD Item") if is_new else frappe.get_doc("RD Item", item_id)
			if is_new:
				doc.item_id, doc.source = item_id, "Other"
			alts = changes.pop("alt_creators", None)
			if "creators" in changes or alts is not None:
				names = changes.pop("creators", None)
				names = names if names is not None else [r.name_as_given or r.creator for r in doc.creators]
				alts = alts or []
				doc.set("creators", [])
				for i, n in enumerate(names):
					doc.append("creators", {"creator": _ensure_creator(n, alts[i] if i < len(alts) else ""),
											"role": "Author", "name_as_given": n[:255]})
			if "subjects" in changes:
				doc.set("subjects", [{"subject": _ensure_subject(s)} for s in changes.pop("subjects")])
			if "curated_collections" in changes:
				ids, created = _collection_names(changes.pop("curated_collections"))
				doc.set("curated_collections", [{"collection": c} for c in ids])
				log += [f"created collection “{c}”" for c in created]
			if "visibility" in changes:
				doc.visibility_set_by = "Manual"
			if "language" in changes:
				from sok_resdesk.core.normalize import normalize_language

				doc.language, doc.language_label = normalize_language(changes.pop("language"))
			if "published" in changes:
				doc.published = 1 if changes.pop("published") else 0
			for key, value in changes.items():
				doc.set(key, value)
			doc.lock_metadata = 1
			doc.flags.skip_search_index = True
			if is_new:
				doc.insert()
			else:
				doc.save()
			frappe.db.commit()
			done.append(item_id)
		except Exception as e:
			frappe.db.rollback()
			log.append(f"FAILED {item_id}: {str(e)[:300]}")
	try:
		for i in range(0, len(done), 200):
			update_item_fields(done[i:i + 200], wait=len(done) <= 200)
	except SearchError as e:
		log.append(f"search index not updated: {e}")
	frappe.db.set_value("RD Metadata Import", name, {
		"status": "Done" if not any(line.startswith("FAILED") for line in log) else "Failed",
		"changed": len(done),
		"preview": "\n".join((log + p["lines"])[:3000]),
	})
	frappe.db.commit()
	return {"message": _("{0} books updated.").format(len(done)) + (f" {len(log)} notes in the log." if log else "")}
