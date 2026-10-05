"""Books from OAI-PMH repositories (DSpace, EPrints, Islandora, OJS…): an Ingest Profile whose
source is *Repository (OAI-PMH)*.

Planning a run harvests the records (``core/harvest.py``): new and changed ones go to batches,
like archive.org's books, and records the repository has deleted are taken off the portal. Each
batch catalogues its records and, when full text is wanted, reads each record's PDF: its text
layer becomes the book's page text (a scan without one is catalogued and waits for OCR). The
repository stays the store of record: the book page links to its record and its PDF.

A run asks only for records changed since the last harvest (``harvested_until``); *Refresh
Items Already in Catalogue* harvests everything again.
"""

from __future__ import annotations

import gzip
import json
import os
from datetime import UTC, datetime

import frappe
import requests
from frappe import _
from frappe.utils import cint

from sok_resdesk.catalogue import item_to_record, upsert_item
from sok_resdesk.core import harvest
from sok_resdesk.core.normalize import normalize_ia_item
from sok_resdesk.core.pdftext import has_text_layer, pages_from_pdf

PART = "oai"  # parts of a harvest, one per batch, kept until the run ends
SCAN = "PDF without text (scan)"  # the same as pdfs.SCAN: a book waiting for OCR
_parts: dict[str, dict] = {}  # this worker's parts read so far: name -> {item_id: record}


def harvester(profile) -> harvest.Harvester:
	return harvest.Harvester(profile.oai_url)


def repository_name(profile) -> str:
	"""The repository's own name (Identify), remembered on the profile's notes cache."""
	key = f"resdesk:oai-name:{profile.oai_url}"
	name = frappe.cache.get_value(key)
	if name is None:
		try:
			name = harvester(profile).identify().get("name") or ""
		except harvest.HarvestError:
			name = ""
		frappe.cache.set_value(key, name, expires_in_sec=7 * 86400)
	return name or profile.profile_name


@frappe.whitelist()
def check(profile: str) -> dict:
	"""Ingest Profile → Check Repository: the repository's name, its sets, and a sample record,
	so a librarian knows the address is right before running."""
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("read")
	h = harvester(doc)
	try:
		info = h.identify()
		sets = h.list_sets()[:500]
		sample = next(h.records(doc.oai_prefix or "oai_dc", doc.oai_set or ""), None)
	except harvest.HarvestError as e:
		frappe.throw(_("The repository did not answer as expected: {0}").format(str(e)[:300]))
	out = {"repository": info, "sets": [{"spec": s, "name": n} for s, n in sets], "sample": None}
	if sample:
		meta = harvest.to_meta(sample)
		out["sample"] = {
			"identifier": sample["identifier"],
			"item_id": harvest.item_id_for(sample["identifier"], doc.id_prefix),
			"title": (meta.get("title") or [""])[0],
			"creators": meta.get("creator", []),
			"date": meta.get("date", ""),
			**harvest.links(sample["dc"]),
		}
	return out


# -- planning -------------------------------------------------------------------------------------


def _parts_dir() -> str:
	return frappe.get_site_path("private", "resdesk-runs")


def _stamp(granularity: str) -> str:
	now = datetime.now(UTC)
	return now.strftime("%Y-%m-%dT%H:%M:%SZ") if "hh" in (granularity or "") else now.strftime("%Y-%m-%d")


def plan(run_name: str, profile, limit: int, log) -> list[list]:
	"""Harvest the records to do: [[item_id, oai identifier, part], …] for the batches. Deleted
	records are taken off the portal here. The records themselves wait in part files, so the
	batches don't ask for them again."""
	h = harvester(profile)
	info = h.identify()
	since = "" if cint(profile.update_existing) else (profile.harvested_until or "")
	started = _stamp(info.get("granularity"))
	log(
		f"Harvesting {info.get('name') or profile.oai_url}"
		+ (f", set {profile.oai_set}" if profile.oai_set else "")
		+ (f", records changed since {since}" if since else ", all records")
	)
	size = max(1, cint(frappe.db.get_single_value("RD Settings", "batch_size")) or 50)
	os.makedirs(_parts_dir(), exist_ok=True)
	entries, part, deleted, seen = [], {}, [], set()

	def write_part():
		name = f"{frappe.scrub(run_name)}-{PART}-{len(entries) // size:05d}.json.gz"
		with gzip.open(os.path.join(_parts_dir(), name), "wt", encoding="utf-8") as f:
			json.dump(part, f, ensure_ascii=False)
		for item_id, rec in part.items():
			entries.append([item_id, rec["identifier"], name])
		part.clear()

	for rec in h.records(profile.oai_prefix or "oai_dc", profile.oai_set or "", since):
		item_id = harvest.item_id_for(rec["identifier"], profile.id_prefix)
		if item_id in seen:
			continue
		seen.add(item_id)
		if rec["deleted"]:
			deleted.append(item_id)
			continue
		part[item_id] = rec
		if len(part) >= size:
			write_part()
		if limit and len(entries) + len(part) >= limit:
			break
		if len(seen) % 5000 == 0:
			log(f"{len(seen):,} records listed so far")
	if part:
		write_part()
	if deleted:
		gone = withdraw(deleted)
		log(f"{len(deleted):,} records deleted in the repository: {gone:,} books taken off the portal")
	if not limit:  # a full listing: the next run asks only for what changed after this one
		frappe.db.set_value(
			"RD Ingest Profile", profile.name, "harvested_until", started, update_modified=False
		)
	log(f"{len(entries):,} records to catalogue")
	return entries


def withdraw(item_ids: list[str]) -> int:
	"""Unpublish books whose records the repository deleted (kept, as archive.org's are)."""
	names = frappe.get_all(
		"RD Item", filters={"name": ("in", item_ids), "published": 1, "source": "Repository"}, pluck="name"
	)
	for name in names:
		doc = frappe.get_doc("RD Item", name)
		doc.published = 0
		doc.removed_from_source = 1
		doc.save(ignore_permissions=True)  # also takes it out of the search index
	return len(names)


def clean_parts(run_name: str) -> None:
	prefix = f"{frappe.scrub(run_name)}-{PART}-"
	folder = _parts_dir()
	if os.path.isdir(folder):
		for name in os.listdir(folder):
			if name.startswith(prefix):
				os.remove(os.path.join(folder, name))


def _record(entry: list, profile) -> dict | None:
	"""The harvested record for a batch entry: from its part, or asked for again (a retry
	after the run ended)."""
	item_id, oai_id = entry[0], entry[1]
	part = os.path.basename(entry[2]) if len(entry) > 2 and entry[2] else ""
	if part:
		if part not in _parts:
			path = os.path.join(_parts_dir(), part)
			try:
				with gzip.open(path, "rt", encoding="utf-8") as f:
					_parts[part] = json.load(f)
			except (OSError, ValueError):
				_parts[part] = {}
			while len(_parts) > 8:  # a worker keeps a few parts, not a whole harvest
				_parts.pop(next(iter(_parts)))
		if item_id in _parts[part]:
			return _parts[part][item_id]
	return harvester(profile).get_record(oai_id, profile.oai_prefix or "oai_dc")


# -- one record -------------------------------------------------------------------------------


def _session() -> requests.Session:
	s = requests.Session()
	s.headers["User-Agent"] = harvest.USER_AGENT
	return s


def trusted_hosts() -> tuple[str, ...]:
	"""The repositories the library set up itself: they may be on its own network. Any other
	address a record gives is fetched only if it is on the public internet (core/netguard.py)."""
	from urllib.parse import urlparse

	urls = frappe.get_all("RD Ingest Profile", filters={"source": "Repository (OAI-PMH)"}, pluck="oai_url")
	return tuple({urlparse(u or "").hostname or "" for u in urls} - {""})


def _get(url: str, **kwargs):
	from sok_resdesk.core import netguard

	return netguard.get(_session(), url, trusted_hosts(), **kwargs)


def find_pdf(landing: str) -> str:
	"""The PDF a record's web page offers (citation_pdf_url, else a PDF link), or ''."""
	from sok_resdesk.core.netguard import Blocked

	try:
		resp = _get(landing, timeout=60)
		if resp.status_code >= 400 or "html" not in resp.headers.get("Content-Type", "html"):
			return ""
		return harvest.pdf_from_landing(resp.text, resp.url)
	except (requests.RequestException, Blocked):
		return ""


def download_pdf(url: str) -> bytes | None:
	"""The PDF, or None when it can't be had (refused, not a PDF, or bigger than MAX_PDF_BYTES)."""
	from sok_resdesk.core.netguard import Blocked

	try:
		with _get(url, timeout=120, stream=True) as resp:
			if resp.status_code >= 400:
				return None
			size = cint(resp.headers.get("Content-Length"))
			if size > harvest.MAX_PDF_BYTES:
				return None
			chunks, total = [], 0
			for chunk in resp.iter_content(1 << 20):
				total += len(chunk)
				if total > harvest.MAX_PDF_BYTES:
					return None
				chunks.append(chunk)
		data = b"".join(chunks)
		return data if data[:5] == b"%PDF-" else None
	except (requests.RequestException, Blocked):
		return None


def read_pdf(url: str) -> tuple[list[dict], int, str]:
	"""(page texts, pages in the PDF, where the text came from) for a record's PDF."""
	data = download_pdf(url) if url else None
	if not data:
		return [], 0, ""
	try:
		pages = pages_from_pdf(data)
	except Exception:  # a damaged PDF: the book is catalogued without its text
		return [], 0, ""
	if has_text_layer(pages):
		return pages, len(pages), "PDF text layer"
	return [], len(pages), SCAN


def ingest_one(entry: list, profile, fetch_text: bool, force: bool = False, buffer=None) -> tuple[str, int]:
	"""Catalogue one harvested record (and its PDF's text). Returns (outcome, pages indexed)."""
	from sok_resdesk.ingest import PAGE_ORDER, cache_enabled, write_cached_pages
	from sok_resdesk.search import SearchError, index_record

	item_id = entry[0]
	rec = _record(entry, profile)
	if rec is None:
		raise harvest.HarvestError(f"{entry[1]} is not in the repository any more")
	if rec["deleted"]:
		withdraw([item_id])
		return "updated", 0
	existing = frappe.db.get_value("RD Item", item_id, ["source_signature", "published"], as_dict=True)
	signature = f"{rec['datestamp']}|{int(bool(fetch_text))}"
	if existing and not force and existing.source_signature == signature:
		return "unchanged", 0

	found = harvest.links(rec["dc"])
	pdf = found["pdf"]
	if not pdf and cint(profile.find_pdf) and found["landing"]:
		pdf = find_pdf(found["landing"])
	meta = harvest.to_meta(rec, repository_name(profile))
	record = normalize_ia_item(item_id, meta, [])
	pages, count, text_source = read_pdf(pdf) if fetch_text else ([], 0, "")
	if text_source == SCAN:
		from sok_resdesk.pdfs import read_ocr_pages

		ocrd = read_ocr_pages(item_id)  # read with OCR here before: still its text
		if ocrd is not None:
			pages, text_source = ocrd, "OCR here"
	restricted = record["access_status"] == "Restricted"
	record.update(
		{
			"source": "Repository",
			"on_archive_org": False,
			"source_url": found["landing"] or pdf,
			"thumbnail_url": "",
			"ark": "",
			"remote_pdf": pdf,
			"oai_identifier": rec["identifier"],
			"page_count": count or record.get("page_count") or 0,
			"has_page_text": bool(pages) and not restricted,
			"has_fulltext": bool(pages) and not restricted,
			"text_source": text_source,
			"source_signature": signature,
			"added_on_source": rec["datestamp"],
		}
	)
	name, created = upsert_item(record, raw={"oai": rec}, profile=profile.name)
	if existing and not existing.published and frappe.db.get_value("RD Item", name, "removed_from_source"):
		# the record came back in the repository: back on the portal
		frappe.db.set_value(
			"RD Item", name, {"published": 1, "removed_from_source": 0}, update_modified=False
		)
	if pages and cache_enabled():
		write_cached_pages(item_id, pages)
	if pages:
		frappe.db.set_value("RD Item", name, "page_order", PAGE_ORDER, update_modified=False)
	if text_source == SCAN and not restricted:
		from sok_resdesk.pdfs import forget_pages, queue_ocr

		forget_pages(item_id)
		queue_ocr(item_id)  # Settings → Catalogue → Read Scans with OCR
	try:
		from sok_resdesk.pagetext import apply

		record = item_to_record(frappe.get_doc("RD Item", name))
		pages = apply(item_id, pages) if not restricted else []
		if buffer is not None:
			return ("created" if created else "updated"), buffer.add(
				record, pages, replace_pages=not created, if_changed=True
			)
		count = index_record(record, pages, replace_pages=not created)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return ("created" if created else "updated"), count


def source_pages(item_id: str) -> list[dict]:
	"""A repository book's page text when the local cache doesn't have it: read its PDF again."""
	url = frappe.db.get_value("RD Item", item_id, "remote_pdf")
	pages, _count, _src = read_pdf(url) if url else ([], 0, "")
	return pages


def refresh(doc) -> None:
	"""Item → Refresh: harvest this one record again, with its PDF."""
	if not doc.oai_identifier or not doc.ingest_profile:
		frappe.throw(_("This book's repository record is not known."))
	profile = frappe.get_doc("RD Ingest Profile", doc.ingest_profile)
	ingest_one([doc.name, doc.oai_identifier], profile, fetch_text=True, force=True)
