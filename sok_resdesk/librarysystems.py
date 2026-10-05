"""A library system's catalogue (Koha, Evergreen, SOUL, e-Granthalaya…) matched to the books here,
and the links sent back (Desk → Library Systems).

1. **Import**: the system's records come as a MARC file (MARCXML or ISO 2709, Koha → Tools →
   Export catalog) or over its OAI-PMH server (``marc21``); each is kept as an RD Library
   Record, with its MARC as received.
2. **Match** (core/libmatch.py): a record that already links to an archive.org book here, or
   has its ISBN, is the same book; otherwise the search engine finds candidates by title and
   they are scored on title (either script), authors and year. A confident match is linked, an
   unsure one waits for a cataloguer (To Review), and a decision a person made is never undone
   by a later import.
3. **Send back**: through a Koha Push Target each linked biblio gets 856 links to the book here
   and on archive.org (its own record, fetched fresh, with only those fields added); for any
   other system, the linked records with their links as MARCXML, to import there.

Book pages show *In the library's catalogue* with a link to the record in its OPAC. Records with
no match can be catalogued here too, so print-only books are found on the portal.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.core import libmatch, marcin

EDITORS = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
MANAGERS = ("System Manager", "ResDesk Manager")
DECIDED = ("Not This Book", "Catalogued")  # a person's (or a cataloguing) decision: kept
CHUNK = 500


def _system(name: str):
	return frappe.get_doc("RD Library System", name)


# -- import -------------------------------------------------------------------------------------


def _marc_bytes(system) -> bytes:
	from frappe.utils.file_manager import get_file_path

	if not system.marc_file:
		frappe.throw(_("Attach the library system's MARC file first."))
	with open(get_file_path(system.marc_file), "rb") as f:
		return f.read()


def records_of(system):
	"""(record, its MARCXML) for every record the system gives."""
	if system.source_kind == "OAI-PMH":
		import xml.etree.ElementTree as ET

		from sok_resdesk.core.harvest import Harvester

		for _ident, deleted, meta in Harvester(system.oai_url).raw_records("marc21", system.oai_set or ""):
			if deleted or meta is None:
				continue
			rec = marcin.record_from_xml(meta)
			yield rec, ET.tostring(meta, encoding="unicode")
	else:
		for rec in marcin.read(_marc_bytes(system)):
			yield rec, marcin.to_xml(rec)


def import_records(system_name: str) -> dict:
	"""Bring the system's records in (a background job), then match them."""
	system = _system(system_name)
	_progress(system_name, _("reading records"))
	seen = new = 0
	for rec, xml in records_of(system):
		s = marcin.summary(rec)
		if not s["id"]:
			continue
		key = f"{system.name}:{s['id']}"[:140]
		values = {
			"title": (s["title"] or "")[:140],
			"alt_title": (s["alt_title"] or "")[:140],
			"creators": "\n".join(s["creators"]),
			"year": s["year"],
			"isbn": s["isbn"],
			"marcxml": xml,
		}
		name = frappe.db.get_value("RD Library Record", {"record_key": key})
		if name:
			frappe.db.set_value("RD Library Record", name, values, update_modified=False)
		else:
			frappe.get_doc(
				{
					"doctype": "RD Library Record",
					"record_key": key,
					"library_system": system.name,
					"record_id": s["id"],
					"status": "New",
					**values,
				}
			).insert(ignore_permissions=True)
			new += 1
		seen += 1
		if seen % CHUNK == 0:
			frappe.db.commit()
			_progress(system_name, _("{0} records read").format(seen))
	frappe.db.set_value(
		"RD Library System", system_name, {"imported_on": now_datetime()}, update_modified=False
	)
	frappe.db.commit()
	result = match_all(system_name)
	return {"records": seen, "new": new, **result}


def _progress(system_name: str, text: str) -> None:
	frappe.db.set_value("RD Library System", system_name, "progress", text[:140], update_modified=False)
	frappe.db.commit()


# -- matching -----------------------------------------------------------------------------------


BOOK_FIELDS = ["name", "item_id", "title", "alt_title", "year", "isbn"]


def _books(names: list[str]) -> list[dict]:
	"""Candidate books with what matching needs (their authors in both forms)."""
	if not names:
		return []
	rows = frappe.get_all("RD Item", filters={"name": ("in", names)}, fields=BOOK_FIELDS)
	creators: dict[str, list[str]] = {}
	for parent, creator, given in frappe.db.sql(
		"""select ic.parent, ic.creator, ic.name_as_given from `tabRD Item Creator` ic
		where ic.parenttype = 'RD Item' and ic.parent in %s""",
		[tuple(names)],
	):
		creators.setdefault(parent, []).extend([c for c in (creator, given) if c])
	for r in rows:
		r["creators"] = creators.get(r["name"], [])
	return rows


def candidates(s: dict) -> list[dict]:
	"""Books here that may be this record: the ones it links to or shares an ISBN with, and what
	the search engine finds for its titles."""
	names: list[str] = []
	if s.get("archive_ids"):
		names += frappe.get_all("RD Item", filters={"name": ("in", s["archive_ids"])}, pluck="name")
	if s.get("isbn"):  # catalogued with or without hyphens
		names += frappe.db.sql_list(
			"select name from `tabRD Item` where replace(replace(isbn, '-', ''), ' ', '') = %s limit 5",
			s["isbn"],
		)
	for title in [t for t in (s.get("title"), s.get("alt_title")) if t]:
		names += _search_titles(title)
	return _books(list(dict.fromkeys(names))[:20])


def _search_titles(title: str) -> list[str]:
	from sok_resdesk.search import MeiliClient, SearchError

	try:
		client = MeiliClient.from_settings()
		hits = client.search(
			client.books, {"q": title[:200], "limit": 8, "attributesToRetrieve": ["item_id"]}
		)
		found = [h["item_id"] for h in hits.get("hits", []) if h.get("item_id")]
		if found:
			return found
	except (SearchError, Exception):
		pass
	# the search engine is away: the longest word of the title, in the catalogue
	words = sorted((w for w in title.split() if len(w) > 3), key=len, reverse=True)
	if not words:
		return []
	return frappe.get_all("RD Item", filters={"title": ("like", f"%{words[0]}%")}, pluck="name", limit=8)


def match_one(name: str) -> str:
	doc = frappe.get_doc("RD Library Record", name)
	if doc.status in DECIDED or (doc.status == "Linked" and doc.decided_by):
		return doc.status
	rec = next(marcin.read((doc.marcxml or "").encode()), None)
	s = marcin.summary(rec) if rec else {"title": doc.title, "creators": (doc.creators or "").splitlines()}
	ranked = libmatch.best(s, candidates(s))
	status = {"Linked": "Linked", "Proposed": "To Review", "No match": "No Match"}[libmatch.decide(ranked)]
	top = ranked[0] if ranked else {}
	doc.update(
		{
			"status": status,
			"item": top.get("item_id") if status in ("Linked", "To Review") else None,
			"score": top.get("score") or 0,
			"why": top.get("why") or "",
			"candidates": json.dumps(ranked[:5], ensure_ascii=False),
		}
	)
	doc.save(ignore_permissions=True)
	return status


def match_all(system_name: str) -> dict:
	names = frappe.get_all(
		"RD Library Record",
		filters={"library_system": system_name, "status": ("not in", DECIDED)},
		pluck="name",
		order_by="creation asc",
	)
	for n, name in enumerate(names, 1):
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		try:
			match_one(name)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Research Desk: library record {name} not matched")
		if n % 100 == 0:
			frappe.db.commit()
			_progress(system_name, _("matching: {0} of {1}").format(n, len(names)))
	frappe.db.commit()
	if cint(frappe.db.get_value("RD Library System", system_name, "catalogue_unmatched")):
		catalogue_unmatched(system_name)
	return counts(system_name)


def counts(system_name: str) -> dict:
	rows = dict(
		frappe.db.sql(
			"select status, count(*) from `tabRD Library Record` where library_system=%s group by status",
			system_name,
		)
	)
	out = {
		"records": sum(rows.values()),
		"linked": rows.get("Linked", 0),
		"proposed": rows.get("To Review", 0),
		"unmatched": rows.get("No Match", 0) + rows.get("Not This Book", 0),
	}
	frappe.db.set_value(
		"RD Library System",
		system_name,
		{**out, "progress": _("{0} linked, {1} to review").format(out["linked"], out["proposed"])},
		update_modified=False,
	)
	frappe.db.commit()
	return out


# -- a person's decisions -------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def decide(record: str, item: str = "", not_a_match: int = 0) -> dict:
	"""Desk: this record is that book (item), or none of the candidates (not_a_match)."""
	frappe.only_for(EDITORS)
	doc = frappe.get_doc("RD Library Record", record)
	if cint(not_a_match):
		doc.update({"status": "Not This Book", "item": None})
	else:
		if not item or not frappe.db.exists("RD Item", item):
			frappe.throw(_("Choose a book here."))
		doc.update({"status": "Linked", "item": item, "why": _("chosen by a cataloguer")})
	doc.decided_by = frappe.session.user
	doc.save()
	counts(doc.library_system)
	return {"status": doc.status, "item": doc.item}


# -- records with no match here -------------------------------------------------------------------


def catalogue_unmatched(system_name: str) -> int:
	"""Records with no book here become catalogue entries (no digital copy; the library's record
	linked), so print-only books are found on the portal."""
	from sok_resdesk.catalogue import upsert_item
	from sok_resdesk.core.normalize import normalize_ia_item

	system = _system(system_name)
	prefix = frappe.scrub(system.name).replace("_", "-")[:20] or "lib"
	done = 0
	for name in frappe.get_all(
		"RD Library Record",
		filters={"library_system": system_name, "status": ("in", ("No Match", "Not This Book"))},
		pluck="name",
	):
		doc = frappe.get_doc("RD Library Record", name)
		rec = next(marcin.read((doc.marcxml or "").encode()), None)
		if rec is None:
			continue
		s = marcin.summary(rec)
		item_id = f"{prefix}-{''.join(ch if ch.isalnum() else '-' for ch in s['id'])}"[:100]
		record = normalize_ia_item(item_id, marcin.to_meta(s, system.system_name), [])
		record.update(
			{
				"source": "Library System",
				"on_archive_org": False,
				"source_url": opac_link(system, s["id"]),
				"thumbnail_url": "",
				"ark": "",
				"has_page_text": False,
				"has_fulltext": False,
				"access_status": "Unknown",
			}
		)
		upsert_item(record, raw={"marcxml": doc.marcxml})
		doc.update({"status": "Catalogued", "item": item_id})
		doc.save(ignore_permissions=True)
		done += 1
	frappe.db.commit()
	return done


def opac_link(system, record_id: str) -> str:
	from urllib.parse import quote

	template = (system.opac_url or "").strip()
	return template.replace("{id}", quote(str(record_id), safe="")) if "{id}" in template else ""


def catalogue_links(item_id: str) -> list[dict]:
	"""The book page: the records of this book in the libraries' catalogues, [{system, url}]."""
	rows = frappe.get_all(
		"RD Library Record",
		filters={"item": item_id, "status": ("in", ("Linked", "Catalogued"))},
		fields=["library_system", "record_id"],
	)
	out = []
	for r in rows:
		system = frappe.get_cached_doc("RD Library System", r.library_system)
		url = opac_link(system, r.record_id)
		if url:
			out.append({"system": system.system_name, "url": url})
	return out


# -- sending links back --------------------------------------------------------------------------


def _links_for(item_id: str, note: str) -> list[tuple[str, str]]:
	from sok_resdesk.catalogue import base_url
	from sok_resdesk.core.seo import book_url

	links = [(book_url(base_url(), item_id), note)]
	if frappe.db.get_value("RD Item", item_id, "on_archive_org"):
		links.append((f"https://archive.org/details/{item_id}", "Internet Archive"))
	return links


def linked(system_name: str, unsent_only: bool = True) -> list:
	filters = {"library_system": system_name, "status": "Linked", "item": ("is", "set")}
	if unsent_only:
		filters["sent_on"] = ("is", "not set")
	return frappe.get_all("RD Library Record", filters=filters, pluck="name", order_by="creation asc")


def send_back(system_name: str) -> dict:
	"""Through the Koha Push Target: each linked biblio gets the 856 links it lacks."""
	from sok_resdesk.outbound import _client

	system = _system(system_name)
	target = frappe.get_doc("RD Push Target", system.push_target) if system.push_target else None
	if not target or target.target_type != "Koha":
		frappe.throw(_("Choose a Koha Push Target to send links back through."))
	koha = _client(target)
	sent = failed = 0
	for name in linked(system_name):
		doc = frappe.get_doc("RD Library Record", name)
		try:
			if target.dry_run:
				state = "dry run: would add links"
			else:
				current = next(marcin.read(koha.get(doc.record_id).encode()))
				updated = marcin.with_links(current, _links_for(doc.item, system.link_note or "Read online"))
				if len(updated.fields) != len(current.fields):
					koha.update(doc.record_id, marcin.collection_xml([updated]))
				state = "sent"
			doc.update({"sent_on": now_datetime(), "send_state": state})
			sent += 1
		except Exception as e:
			doc.send_state = f"failed: {str(e)[:120]}"
			failed += 1
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	return {"sent": sent, "failed": failed}


@frappe.whitelist()
def download_with_links(system: str) -> None:
	"""The linked records as the library system gave them, with the 856 links added: MARCXML to
	import back there (matching on the record number to overlay)."""
	frappe.only_for(EDITORS)
	doc = _system(system)
	records = []
	for name in linked(system, unsent_only=False):
		r = frappe.get_doc("RD Library Record", name)
		rec = next(marcin.read((r.marcxml or "").encode()), None)
		if rec is not None:
			records.append(marcin.with_links(rec, _links_for(r.item, doc.link_note or "Read online")))
	frappe.response["type"] = "download"
	frappe.response["filename"] = f"{frappe.scrub(doc.name)}-with-links.xml"
	frappe.response["filecontent"] = marcin.collection_xml(records)
	frappe.response["content_type"] = "application/marcxml+xml"


# -- the Desk's buttons -----------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def start(system: str, action: str = "import") -> dict:
	"""Library System form: Import Now, Match Again or Send Links Back, in the background."""
	frappe.only_for(MANAGERS if action == "send" else EDITORS)
	method = {
		"import": "sok_resdesk.librarysystems.import_records",
		"match": "sok_resdesk.librarysystems.match_all",
		"send": "sok_resdesk.librarysystems.send_back",
	}.get(action)
	if not method:
		frappe.throw(_("Unknown action"))
	_system(system).check_permission("write")
	frappe.enqueue(
		method,
		queue="long",
		timeout=6 * 3600,
		job_id=f"resdesk-libsys-{action}-{system}",
		deduplicate=True,
		system_name=system,
	)
	_progress(
		system,
		{
			"import": _("waiting to import"),
			"match": _("waiting to match"),
			"send": _("waiting to send links"),
		}[action],
	)
	return {"queued": True}
