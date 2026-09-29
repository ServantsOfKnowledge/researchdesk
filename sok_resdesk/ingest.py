"""Ingest from the Internet Archive into the catalogue and search index.

Flow for one run:
  profile -> IA query -> scrape identifiers (cursor) -> for each item:
    metadata API -> normalise -> upsert RD Item -> fetch page text -> index
Runs as a background job (queue "long"); progress is written to RD Ingest Run.
"""

from __future__ import annotations

import traceback

import frappe
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import item_to_record, settings, upsert_item
from sok_resdesk.core.ia import IAClient, IAError
from sok_resdesk.core.normalize import normalize_ia_item

COMMIT_EVERY = 1  # items are slow (several HTTP calls each), so saving progress every item is cheap


def client() -> IAClient:
	s = settings()
	return IAClient(contact=s.ia_contact or "", delay=float(s.ia_delay or 0.5))


def fetch_pages(item_id: str, ia: IAClient | None = None, page_numbers: dict | None = None) -> list[dict]:
	ia = ia or client()
	if page_numbers is None:
		try:
			page_numbers = ia.metadata(item_id).get("page_numbers")
		except IAError:
			page_numbers = None
	return ia.page_texts(item_id, page_numbers)


# -- whitelisted UI actions ---------------------------------------------------------

@frappe.whitelist()
def count_profile(profile: str) -> dict:
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("read")
	query = doc.build_query()
	count = client().count(query)
	frappe.db.set_value("RD Ingest Profile", profile, "matching_count", count)
	return {"count": count, "query": query}


@frappe.whitelist()
def start_ingest(profile: str, triggered_by: str = "Manual") -> str:
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("write")
	run = create_run(doc, triggered_by)
	frappe.enqueue(
		"sok_resdesk.ingest.run_ingest", queue="long", timeout=12 * 3600, run_name=run.name,
		enqueue_after_commit=True,
	)
	return run.name


@frappe.whitelist()
def refresh_item(item_id: str) -> str:
	frappe.only_for(("System Manager", "ResDesk Manager", "ResDesk Cataloguer"))
	ia = client()
	profile = frappe.db.get_value("RD Item", item_id, "ingest_profile")
	_ingest_one(ia, item_id, profile, fetch_text=True)
	frappe.db.commit()
	return item_id


# -- core job ---------------------------------------------------------------------------

def create_run(profile_doc, triggered_by: str = "Manual"):
	run = frappe.get_doc({
		"doctype": "RD Ingest Run",
		"profile": profile_doc.name,
		"status": "Queued",
		"query": profile_doc.build_query(),
		"triggered_by": triggered_by,
	}).insert(ignore_permissions=True)
	frappe.db.set_value("RD Ingest Profile", profile_doc.name, {
		"last_run": run.name, "last_run_on": now_datetime(), "last_status": "Queued",
	})
	frappe.db.commit()
	return run


def _ingest_one(ia: IAClient, item_id: str, profile: str | None, fetch_text: bool) -> tuple[bool, int]:
	"""Fetch, store and index one item. Returns (created, pages_indexed)."""
	from sok_resdesk.search import SearchError, index_record

	data = ia.metadata(item_id)
	meta, files = data.get("metadata", {}), data.get("files", [])
	record = normalize_ia_item(item_id, meta, files)
	name, created = upsert_item(record, raw=meta, profile=profile)

	pages: list[dict] = []
	if fetch_text and record["has_page_text"]:
		pages = ia.page_texts(item_id, data.get("page_numbers"))
	try:
		count = index_record(item_to_record(frappe.get_doc("RD Item", name)), pages)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return created, count


def run_ingest(run_name: str, verbose: bool = False, limit_override: int | None = None) -> None:
	run = frappe.get_doc("RD Ingest Run", run_name)
	profile = frappe.get_doc("RD Ingest Profile", run.profile)
	ia = client()
	log: list[str] = []

	def note(msg: str):
		line = f"{now_datetime().strftime('%H:%M:%S')} {msg}"
		log.append(line)
		if verbose:
			print(line)

	def save(status: str | None = None):
		if status:
			run.status = status
		run.log = "\n".join(log[-2000:])
		run.db_update()
		frappe.db.set_value("RD Ingest Profile", profile.name, "last_status", run.status, update_modified=False)
		frappe.db.commit()

	run.status, run.started_on = "Running", now_datetime()
	only_new = run.triggered_by == "Scheduler" or not cint(profile.update_existing)
	counts = {"processed": 0, "created_count": 0, "updated_count": 0, "skipped_count": 0, "failed_count": 0}
	try:
		from sok_resdesk.search import MeiliClient, SearchError

		try:
			MeiliClient.from_settings().setup()
		except SearchError as e:
			note(f"WARNING search engine unavailable, items will be catalogued but not searchable: {e}")

		query = profile.build_query()
		run.total_found = ia.count(query)
		limit = cint(profile.max_items) if limit_override is None else cint(limit_override)
		note(f"Query: {query}")
		note(f"{run.total_found} items match on IA; ingesting {'all' if not limit else min(limit, run.total_found)}")
		if limit:
			run.total_found = min(limit, run.total_found)
		save()

		for item_id in ia.iter_identifiers(query, limit=limit):
			counts["processed"] += 1
			try:
				if only_new and frappe.db.exists("RD Item", item_id):
					counts["skipped_count"] += 1
				else:
					created, pages = _ingest_one(ia, item_id, profile.name, bool(cint(profile.fetch_fulltext)))
					counts["created_count" if created else "updated_count"] += 1
					note(f"{'NEW' if created else 'UPD'} {item_id} ({pages} pages indexed)")
			except Exception as e:
				frappe.db.rollback()
				counts["failed_count"] += 1
				note(f"FAIL {item_id}: {e}")
				if verbose:
					traceback.print_exc()
			if counts["processed"] % COMMIT_EVERY == 0:
				run.update(counts)
				save()
		run.update(counts)
		run.finished_on = now_datetime()
		note(
			f"Done: {counts['created_count']} new, {counts['updated_count']} updated, "
			f"{counts['skipped_count']} skipped, {counts['failed_count']} failed"
		)
		save("Completed with Errors" if counts["failed_count"] else "Completed")
	except Exception as e:
		frappe.db.rollback()
		run.update(counts)
		run.finished_on = now_datetime()
		note(f"FAILED: {e}\n{traceback.format_exc()}")
		save("Failed")
		frappe.log_error("Research Desk: ingest run failed", traceback.format_exc())


# -- scheduler --------------------------------------------------------------------------

def _run_scheduled(schedule: str):
	for name in frappe.get_all("RD Ingest Profile", filters={"enabled": 1, "schedule": schedule}, pluck="name"):
		running = frappe.db.exists("RD Ingest Run", {"profile": name, "status": ("in", ["Queued", "Running"])})
		if running:
			continue
		run = create_run(frappe.get_doc("RD Ingest Profile", name), "Scheduler")
		frappe.enqueue("sok_resdesk.ingest.run_ingest", queue="long", timeout=12 * 3600, run_name=run.name)


def run_scheduled_daily():
	_run_scheduled("Daily")


def run_scheduled_weekly():
	_run_scheduled("Weekly")


def ensure_profile(name: str, **values) -> str:
	"""Create or update a profile (used by the CLI and the sample data)."""
	if frappe.db.exists("RD Ingest Profile", name):
		doc = frappe.get_doc("RD Ingest Profile", name)
		doc.update({k: v for k, v in values.items() if v is not None})
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "RD Ingest Profile", "profile_name": name, **values})
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name
