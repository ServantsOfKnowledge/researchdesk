"""Catalogue helpers: settings, upserting RD Item records, and turning them into plain dicts."""

from __future__ import annotations

import json

import frappe
from frappe.utils import get_url, now_datetime

from sok_resdesk.core.normalize import decade_of


def settings():
	return frappe.get_cached_doc("RD Settings")


def base_url() -> str:
	return (settings().base_url or get_url()).rstrip("/")


def portal_title() -> str:
	return settings().portal_title or "SOK Research Desk"


# -- read ---------------------------------------------------------------------


def item_to_record(doc) -> dict:
	"""RD Item document -> plain dict (the shape the core/ modules expect)."""
	creators, alt_creators, creator_ids = [], [], []
	for row in doc.creators or []:
		creators.append(row.name_as_given or row.creator)
		c = (
			frappe.db.get_value(
				"RD Creator", row.creator, ["alt_name", "wikidata_id", "viaf_id"], as_dict=True
			)
			if row.creator
			else None
		) or {}
		alt_creators.append(c.get("alt_name") or "")
		# the person's identifiers once matched (Desk → Authorities): exports and JSON-LD carry them
		creator_ids.append({"wikidata": c.get("wikidata_id") or "", "viaf": c.get("viaf_id") or ""})
	subject_ids = {}
	if doc.subjects:
		for s in frappe.get_all(
			"RD Subject",
			filters={"name": ("in", [r.subject for r in doc.subjects]), "lcsh_id": ("is", "set")},
			fields=["name", "lcsh_id", "lcsh_label"],
		):
			subject_ids[s.name] = {"lcsh": s.lcsh_id, "label": s.lcsh_label or s.name}
	return {
		"item_id": doc.item_id,
		"source": doc.source,
		"item_type": doc.get("item_type") or "Book",
		"title": doc.title,
		"alt_title": doc.alt_title or "",
		"creators": creators,
		"alt_creators": alt_creators,
		"creator_ids": creator_ids,
		"subject_ids": subject_ids,
		"year": doc.year or None,
		"decade": decade_of(doc.year),
		"date_raw": doc.date_raw or "",
		"publisher": doc.publisher or "",
		"place": doc.place or "",
		"language": doc.language or "",
		"language_label": doc.language_label or "",
		"series": doc.series or "",
		"isbn": doc.isbn or "",
		"page_count": doc.page_count or 0,
		"description": doc.description or "",
		"subjects": [r.subject for r in doc.subjects or []],
		"collections": [c for c in (doc.collections or "").splitlines() if c.strip()],
		"licence_url": doc.licence_url or "",
		"rights": doc.rights or "",
		"access_status": doc.access_status or "Unknown",
		"visibility": doc.visibility or "Public",
		"source_url": doc.source_url or "",
		"thumbnail_url": _absolute(doc.thumbnail_url or ""),
		"ark": doc.ark or "",
		"persistent_id": (doc.get("persistent_id") or "") if _arks_on() else "",
		# only a DOI that resolves is cited (DataCite's test system makes ones that don't)
		"doi": doc.get("doi") if doc.get("doi_state") == "Findable" else "",
		"has_fulltext": bool(doc.has_fulltext),
		"has_page_text": bool(doc.has_page_text),
		"on_archive_org": (bool(doc.on_archive_org) or doc.source == "Internet Archive")
		and not doc.get("served_from_copy"),
		"served_from_copy": bool(doc.get("served_from_copy")),
		"local_pdf": doc.local_pdf or "",
		"pdf_url": _pdf_url(doc),
		"from_repository": doc.source == "Repository",
		"modified": doc.modified,
		"curated_collections": [r.collection for r in doc.get("curated_collections") or []],
		"set_specs": [c for c in (doc.collections or "").splitlines() if c.strip()]
		+ [f"rd:{r.collection}" for r in doc.get("curated_collections") or []],
		**_note_labels(doc.item_id),
	}


def _note_labels(item_id: str) -> dict:
	"""Tags and Wikidata items from the book's public notes (searched with the book)."""
	try:
		from sok_resdesk.annotations import public_labels

		return public_labels(item_id)
	except Exception:  # e.g. during install, before the notes table exists
		return {}


def _arks_on() -> bool:
	"""Settings → Persistent Identifiers → Give Books ARKs: until then no ARK shows anywhere."""
	return bool(frappe.db.get_single_value("RD Settings", "ark_enabled"))


def _absolute(url: str) -> str:
	return f"{base_url()}{url}" if url.startswith("/") else url


def _pdf_url(doc) -> str:
	"""Where readers can download the PDF: archive.org, this portal for local-only books and for
	books served from our preservation copy, or the repository a book was harvested from."""
	from urllib.parse import quote

	if doc.get("served_from_copy"):
		from sok_resdesk.preservation import copy_pdf

		found = copy_pdf(doc.item_id)
		if found:
			return f"{base_url()}/api/method/sok_resdesk.api.file?item_id={quote(doc.item_id, safe='')}&name={quote(found[0], safe='')}"
		return ""
	if doc.source == "Internet Archive" or doc.on_archive_org:
		return f"https://archive.org/download/{doc.item_id}/{doc.item_id}.pdf"
	if doc.local_pdf:
		return f"{base_url()}/api/method/sok_resdesk.api.file?item_id={quote(doc.item_id, safe='')}&name={quote(doc.local_pdf, safe='')}"
	return doc.get("remote_pdf") or ""  # a repository's own PDF


def get_record(item_id: str, published_only: bool = True, check_access: bool = True) -> dict | None:
	"""A published record, or None if it doesn't exist or the current visitor may not find it."""
	if not item_id or not frappe.db.exists("RD Item", item_id):
		return None
	doc = frappe.get_doc("RD Item", item_id)
	if published_only and not doc.published:
		return None
	if check_access:
		from sok_resdesk.access import can_find

		if not can_find(doc.visibility):
			return None
	return item_to_record(doc)


# -- write --------------------------------------------------------------------


def _ensure_creator(name: str, alt: str = "") -> str:
	name = name.strip()[:140]
	if not frappe.db.exists("RD Creator", name):
		frappe.get_doc({"doctype": "RD Creator", "full_name": name, "alt_name": alt[:255]}).insert(
			ignore_permissions=True
		)
	elif alt and not frappe.db.get_value("RD Creator", name, "alt_name"):
		frappe.db.set_value("RD Creator", name, "alt_name", alt[:255])
	return name


def _ensure_subject(name: str) -> str:
	name = name.strip()[:140]
	if not frappe.db.exists("RD Subject", name):
		frappe.get_doc({"doctype": "RD Subject", "subject_name": name}).insert(ignore_permissions=True)
	return name


# What a cataloguer edits. When an item has "Keep My Edits" on, re-ingesting leaves these alone.
DESCRIPTIVE = (
	"title",
	"alt_title",
	"date_raw",
	"year",
	"language",
	"language_label",
	"publisher",
	"place",
	"series",
	"isbn",
	"description",
	"licence_url",
	"rights",
	"item_type",
)


def upsert_item(
	record: dict, raw: dict | None = None, profile: str | None = None, quick: bool = False
) -> tuple[str, bool]:
	"""Create or update an RD Item from a normalised record. Returns (name, created).
	`quick`: catalogued from archive.org's search record only (ingest's first pass); its full
	record and page text follow in the background (details_pending)."""
	exists = frappe.db.exists("RD Item", record["item_id"])
	if not exists:
		from sok_resdesk.capacity import check_room

		check_room(record)  # Settings → Machine Resources → Book Limit
	doc = frappe.get_doc("RD Item", record["item_id"]) if exists else frappe.new_doc("RD Item")
	locked = bool(exists and doc.get("lock_metadata"))
	doc.flags.from_ingest = True

	simple = (
		"item_id",
		"source",
		"title",
		"alt_title",
		"date_raw",
		"year",
		"language",
		"language_label",
		"publisher",
		"place",
		"series",
		"isbn",
		"page_count",
		"description",
		"licence_url",
		"rights",
		"access_status",
		"source_url",
		"thumbnail_url",
		"ark",
		"ocr_engine",
		"ocr_language",
		"scanning_centre",
		"added_on_source",
		"local_store",
		"local_path",
		"local_pdf",
		"local_thumb",
		"text_source",
		"source_signature",
		"item_type",
		"oai_identifier",
		"remote_pdf",
	)
	for field in simple:
		if locked and field in DESCRIPTIVE:
			continue
		if field == "item_type" and not record.get(field):
			continue
		value = record.get(field)
		if isinstance(value, str):
			limit = (
				1000
				if field in ("title", "alt_title")
				else 500
				if field in ("publisher", "licence_url", "series", "source_url")
				else None
			)
			if limit:
				value = value[:limit]
		doc.set(field, value)
	doc.has_fulltext = 1 if record.get("has_fulltext") else 0
	doc.has_page_text = 1 if record.get("has_page_text") else 0
	doc.on_archive_org = 1 if record.get("on_archive_org", record.get("source") == "Internet Archive") else 0
	doc.collections = "\n".join(record.get("collections") or [])

	alts = record.get("alt_creators") or []
	if locked:
		return _save_ingested(doc, exists, raw, profile, record, quick)
	doc.set("creators", [])
	seen = set()
	for i, name in enumerate(record.get("creators") or []):
		creator = _ensure_creator(name, alts[i] if i < len(alts) else "")
		if creator in seen:
			continue
		seen.add(creator)
		doc.append("creators", {"creator": creator, "role": "Author", "name_as_given": name[:255]})

	doc.set("subjects", [])
	seen = set()
	for subject in record.get("subjects") or []:
		name = _ensure_subject(subject)
		if name not in seen:
			seen.add(name)
			doc.append("subjects", {"subject": name})

	return _save_ingested(doc, exists, raw, profile, record, quick)


def _save_ingested(doc, exists, raw, profile, record, quick: bool = False) -> tuple[str, bool]:
	if raw is not None:
		doc.raw_metadata = json.dumps(raw, ensure_ascii=False)[:500000]
	if profile:
		doc.ingest_profile = profile
	if not exists:
		from sok_resdesk.access import initial_visibility
		from sok_resdesk.curation import collections_for_new_item

		doc.visibility, doc.visibility_set_by = initial_visibility(record, profile)
		for c in collections_for_new_item({**record, "item_type": doc.item_type}, profile):
			doc.append("curated_collections", {"collection": c})
	if quick:
		doc.details_pending = 1  # last_ingested stays empty: the book is not fully in yet
	else:
		doc.details_pending = 0
		doc.last_ingested = now_datetime()
	doc.flags.skip_search_index = True  # the ingest job indexes with page text itself
	if exists:
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)
	return doc.name, not exists
