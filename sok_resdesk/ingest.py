"""Ingest from the Internet Archive into the catalogue and search index.

A run has two phases:

1. **Plan** (one job): run the IA query, list identifiers with the scrape cursor,
   drop the ones already catalogued (unless refreshing), and split the rest
   into batches.
2. **Work** (many jobs): each batch is its own background job on the "long"
   queue. With N queue workers, N batches run at once. Per book:
   metadata API -> normalise -> upsert RD Item -> page text (cache or IA) -> index.

Progress counters on RD Ingest Run are updated with atomic SQL increments, so
parallel batches never overwrite each other. The last batch to finish closes
the run. Command-line runs can use the same code in the foreground.
"""

from __future__ import annotations

import gzip
import json
import os
import time
import traceback

import frappe
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import item_to_record, settings, upsert_item
from sok_resdesk.core.ia import IAClient, IAError
from sok_resdesk.core.normalize import normalize_ia_item
from sok_resdesk.holding import hold_when_paused

RUN = "tabRD Ingest Run"
JOB_TIMEOUT = 6 * 3600
MAX_LOG_CHARS = 200_000


def client() -> IAClient:
	s = settings()
	return IAClient(contact=s.ia_contact or "", delay=float(s.ia_delay or 0.5))


# -- page-text cache ----------------------------------------------------------------------


def _cache_path(item_id: str) -> str:
	safe = item_id.replace("/", "_")
	return frappe.get_site_path("private", "resdesk-pages", safe[:2].lower(), f"{safe}.json.gz")


def cache_enabled() -> bool:
	value = settings().get("cache_page_text")
	return True if value is None else bool(cint(value))


def read_cached_pages(item_id: str) -> list[dict] | None:
	path = _cache_path(item_id)
	if not os.path.exists(path):
		return None
	try:
		with gzip.open(path, "rt", encoding="utf-8") as f:
			return json.load(f)
	except (OSError, ValueError):
		return None


def write_cached_pages(item_id: str, pages: list[dict]) -> None:
	path = _cache_path(item_id)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = f"{path}.tmp"
	with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
		json.dump(pages, f, ensure_ascii=False)
	os.replace(tmp, path)


def fetch_pages(
	item_id: str, ia: IAClient | None = None, page_numbers: dict | None = None, refresh: bool = False
) -> list[dict]:
	"""Page texts for one book: local cache first, then the Internet Archive."""
	use_cache = cache_enabled()
	if use_cache and not refresh:
		cached = read_cached_pages(item_id)
		if cached is not None:
			return cached
	local = frappe.db.get_value("RD Item", item_id, ["source", "local_store", "local_path"], as_dict=True)
	if local and local.source == "Local":
		from sok_resdesk.local_source import sections_from_text, store_for_item

		store = store_for_item(frappe.get_doc("RD Item", item_id))
		if not store:
			return []
		data = store.load_item(item_id, local.local_path)
		pages, _src = store.page_texts(item_id, local.local_path, data.get("page_numbers"))
		if not pages:
			pages = sections_from_text(store.book_text(item_id, local.local_path))
		if use_cache and pages:
			write_cached_pages(item_id, pages)
		return pages
	ia = ia or client()
	if page_numbers is None:
		try:
			page_numbers = ia.metadata(item_id).get("page_numbers")
		except IAError:
			page_numbers = None
	pages = ia.page_texts(item_id, page_numbers)
	if use_cache and pages:
		write_cached_pages(item_id, pages)
	return pages


# -- whitelisted UI actions ---------------------------------------------------------


@frappe.whitelist()
def count_profile(profile: str) -> dict:
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("read")
	query = doc.build_query()
	if doc.is_folder:
		from sok_resdesk.local_source import open_profile_store

		count = sum(1 for _ in open_profile_store(doc).iter_items())
	else:
		count = client().count(query)
	frappe.db.set_value("RD Ingest Profile", profile, "matching_count", count)
	from sok_resdesk.capacity import status

	room = status()
	return {"count": count, "query": query, "room": room["remaining_books"], "limit": room["limit_books"]}


@frappe.whitelist()
def start_ingest(profile: str, triggered_by: str = "Manual") -> str:
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("write")
	run = create_run(doc, triggered_by)
	enqueue_plan(run.name)
	return run.name


@frappe.whitelist()
def cancel_run(run: str) -> None:
	"""Kept for API compatibility: stops the run and removes its queued batches."""
	from sok_resdesk.jobs import stop_run

	stop_run(run)


@frappe.whitelist()
def refresh_item(item_id: str) -> str:
	frappe.only_for(("System Manager", "ResDesk Manager", "ResDesk Cataloguer"))
	doc = frappe.get_doc("RD Item", item_id)
	if doc.source == "Local":
		from sok_resdesk.local_source import ingest_local_one, store_for_item

		store = store_for_item(doc)
		if not store:
			frappe.throw(frappe._("The folder or server for this item is not reachable."))
		profile = (
			frappe.get_doc("RD Ingest Profile", doc.ingest_profile)
			if doc.ingest_profile
			else frappe._dict(name=None, check_archive_org=1)
		)
		ingest_local_one(store, item_id, doc.local_path, profile, fetch_text=True, force=True)
	else:
		_ingest_one(client(), item_id, doc.ingest_profile, fetch_text=True, refresh=True)
	frappe.db.commit()
	return item_id


# -- one item -----------------------------------------------------------------------------


def _ingest_one(
	ia: IAClient, item_id: str, profile: str | None, fetch_text: bool, refresh: bool = False
) -> tuple[bool, int]:
	"""Fetch, store and index one item. Returns (created, pages_indexed)."""
	from sok_resdesk.search import SearchError, index_record

	data = ia.metadata(item_id)
	meta, files = data.get("metadata", {}), data.get("files", [])
	record = normalize_ia_item(item_id, meta, files)
	name, created = upsert_item(record, raw=meta, profile=profile)

	pages: list[dict] = []
	if fetch_text and record["has_page_text"]:
		pages = fetch_pages(item_id, ia, data.get("page_numbers"), refresh=refresh)
	try:
		count = index_record(
			item_to_record(frappe.get_doc("RD Item", name)), pages, replace_pages=not created
		)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return created, count


# -- runs -----------------------------------------------------------------------------------


def create_run(profile_doc, triggered_by: str = "Manual"):
	run = frappe.get_doc(
		{
			"doctype": "RD Ingest Run",
			"profile": profile_doc.name,
			"status": "Queued",
			"query": profile_doc.build_query(),
			"triggered_by": triggered_by,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		"RD Ingest Profile",
		profile_doc.name,
		{
			"last_run": run.name,
			"last_run_on": now_datetime(),
			"last_status": "Queued",
		},
	)
	frappe.db.commit()
	return run


def enqueue_plan(run_name: str, limit_override: int | None = None) -> None:
	frappe.enqueue(
		"sok_resdesk.ingest.plan_run",
		queue="long",
		timeout=JOB_TIMEOUT,
		run_name=run_name,
		limit_override=limit_override,
		enqueue_after_commit=True,
		job_id=f"resdesk-plan-{run_name}",
	)


def _log(run_name: str, msg: str, verbose: bool = False) -> None:
	line = f"{now_datetime().strftime('%H:%M:%S')} {msg}\n"
	if verbose:
		print(line, end="")
	frappe.db.sql(
		f"update `{RUN}` set log = right(concat(ifnull(log,''), %s), {MAX_LOG_CHARS}) where name=%s",
		(line, run_name),
	)


def _bump(run_name: str, **counts) -> None:
	sets = ", ".join(f"`{k}` = ifnull(`{k}`,0) + %({k})s" for k in counts)
	frappe.db.sql(
		f"update `{RUN}` set {sets}, modified=%(now)s where name=%(name)s",
		{**counts, "name": run_name, "now": now_datetime()},
	)


def _set_status(run_name: str, status: str) -> None:
	frappe.db.sql(f"update `{RUN}` set status=%s where name=%s", (status, run_name))
	profile = frappe.db.get_value("RD Ingest Run", run_name, "profile")
	frappe.db.set_value("RD Ingest Profile", profile, "last_status", status, update_modified=False)


def _is_cancelled(run_name: str) -> bool:
	return _status(run_name) == "Cancelled"


def _status(run_name: str, lock: bool = False) -> str:
	return frappe.db.sql(
		f"select status from `{RUN}` where name=%s{' for update' if lock else ''}", run_name
	)[0][0]


def hold_work(run_name: str, items: list | None = None, plan: bool = False) -> None:
	"""Keep books a paused run hasn't done yet (call with the run row locked)."""
	row = frappe.db.sql(f"select held_work from `{RUN}` where name=%s for update", run_name)[0][0]
	try:
		held = json.loads(row) if row else {}
	except ValueError:
		held = {}
	held["items"] = (held.get("items") or []) + list(items or [])
	held["plan"] = bool(held.get("plan") or plan)
	frappe.db.sql(f"update `{RUN}` set held_work=%s where name=%s", (json.dumps(held), run_name))


def _paused_here(run_name: str, remaining: list, batch_no: int, verbose: bool = False) -> bool:
	"""The run was paused: if it still is (checked under the row lock, so a Resume at the same
	moment can't be missed), keep the remaining books on the run and stop this batch."""
	frappe.db.commit()
	if _status(run_name, lock=True) != "Paused":
		frappe.db.commit()
		return False
	hold_work(run_name, remaining)
	frappe.db.commit()
	_log(run_name, f"batch {batch_no}: paused, {len(remaining)} books kept for later", verbose)
	frappe.db.commit()
	return True


@hold_when_paused("long")
def plan_run(
	run_name: str, limit_override: int | None = None, foreground: bool = False, verbose: bool = False
) -> list[list[str]]:
	"""List what to ingest, split it into batches and queue them (or return them)."""
	from sok_resdesk.search import MeiliClient, SearchError

	run = frappe.get_doc("RD Ingest Run", run_name)
	if run.status in ("Cancelled", "Paused"):
		return []  # stopped or paused before this job started (a paused plan is kept on the run)
	profile = frappe.get_doc("RD Ingest Profile", run.profile)
	ia = client()
	frappe.db.sql(
		f"update `{RUN}` set status='Running', started_on=ifnull(started_on, %s) where name=%s",
		(now_datetime(), run_name),
	)
	frappe.db.commit()
	try:
		try:
			MeiliClient.from_settings().setup()
		except SearchError as e:
			_log(
				run_name,
				f"WARNING search engine unavailable; items will be catalogued but not searchable: {e}",
				verbose,
			)

		query = profile.build_query()
		limit = cint(profile.max_items) if limit_override is None else cint(limit_override)
		only_new = run.triggered_by == "Scheduler" or not cint(profile.update_existing)
		skipped = 0
		if profile.is_folder:
			# Every item goes to a batch: unchanged ones are skipped there by comparing
			# file signatures, so new *and* changed books are picked up.
			from sok_resdesk.local_source import open_profile_store

			store = open_profile_store(profile)
			_log(run_name, f"Scanning {profile.location} for item folders (…/<id>/<id>_meta.xml)", verbose)
			pairs = list(store.iter_items(limit=limit))
			seen: set[str] = set()
			ids = []
			for item_id, loc in pairs:
				if item_id in seen:
					_log(run_name, f"DUPLICATE identifier {item_id} at {loc}; keeping the first", verbose)
					continue
				seen.add(item_id)
				ids.append([item_id, loc])
			_log(run_name, f"{len(ids):,} item folders found", verbose)
			only_new = False
		else:
			matching = ia.count(query)
			_log(run_name, f"Query: {query}", verbose)
			_log(
				run_name,
				f"{matching:,} items match on IA; taking {'all' if not limit else f'up to {limit:,}'}",
				verbose,
			)
			ids = list(dict.fromkeys(ia.iter_identifiers(query, limit=limit)))
		if only_new and ids:
			existing: set[str] = set()
			for i in range(0, len(ids), 1000):
				existing.update(
					frappe.get_all("RD Item", filters={"name": ("in", ids[i : i + 1000])}, pluck="name")
				)
			skipped = len(existing)
			ids = [i for i in ids if i not in existing]

		size = max(1, cint(settings().get("batch_size")) or 50)
		batches = [ids[i : i + size] for i in range(0, len(ids), size)]
		frappe.db.sql(
			f"update `{RUN}` set total_found=%s, skipped_count=%s, processed=%s, chunks_total=%s, pending_chunks=%s "
			"where name=%s",
			(len(ids) + skipped, skipped, skipped, len(batches), len(batches), run_name),
		)
		_log(
			run_name,
			f"{len(ids):,} to process, {skipped:,} already in the catalogue; {len(batches)} batch(es) of up to {size}",
			verbose,
		)
		frappe.db.commit()

		if not batches:
			_finish(run_name, verbose)
			return []
		if not foreground:
			if _status(run_name, lock=True) == "Paused":  # paused while listing: keep it all for Resume
				hold_work(run_name, ids)
				frappe.db.sql(f"update `{RUN}` set pending_chunks=0 where name=%s", run_name)
				_log(run_name, f"paused: {len(ids):,} books kept for later", verbose)
				frappe.db.commit()
				return []
			frappe.db.commit()
			for n, batch in enumerate(batches, 1):
				frappe.enqueue(
					"sok_resdesk.ingest.run_batch",
					queue="long",
					timeout=JOB_TIMEOUT,
					run_name=run_name,
					item_ids=batch,
					batch_no=n,
					job_id=f"resdesk-{run_name}-{n}",
				)
		return batches
	except Exception as e:
		frappe.db.rollback()
		_log(run_name, f"FAILED while planning: {e}\n{traceback.format_exc()}", verbose)
		frappe.db.sql(
			f"update `{RUN}` set status='Failed', finished_on=%s where name=%s", (now_datetime(), run_name)
		)
		frappe.db.commit()
		frappe.log_error("Research Desk: ingest planning failed", traceback.format_exc())
		return []


def run_batch(run_name: str, item_ids: list, batch_no: int = 0, verbose: bool = False) -> None:
	"""Ingest one batch. Items are IA identifiers, or [identifier, folder] pairs for folder
	sources. Safe to run many at once."""
	profile_name = frappe.db.get_value("RD Ingest Run", run_name, "profile")
	profile = frappe.get_doc("RD Ingest Profile", profile_name)
	fetch_text = bool(cint(profile.fetch_fulltext))
	refresh = bool(cint(profile.update_existing))
	ia = client()
	store = None
	if profile.is_folder:
		from sok_resdesk.local_source import ingest_local_one, open_profile_store

		store = open_profile_store(profile)
	from sok_resdesk.capacity import BookLimitReached, has_room

	limit_told = False
	for pos, entry in enumerate(item_ids):
		item_id, loc = (entry[0], entry[1]) if isinstance(entry, (list, tuple)) else (entry, None)
		frappe.db.commit()  # start each item with a fresh snapshot
		status = _status(run_name)
		if status == "Cancelled":
			_log(run_name, f"batch {batch_no}: cancelled", verbose)
			break
		if status == "Paused" and _paused_here(run_name, item_ids[pos:], batch_no, verbose):
			break
		# at the book limit, books already in the catalogue are still updated; new ones wait
		if not frappe.db.exists("RD Item", item_id) and not has_room():
			if not limit_told:
				_log(run_name, f"batch {batch_no}: book limit reached: new books are skipped", verbose)
				limit_told = True
			_bump(run_name, processed=1, skipped_count=1)
			frappe.db.commit()
			continue
		error = None
		for attempt in range(3):
			try:
				if store is not None:
					outcome, pages = ingest_local_one(store, item_id, loc, profile, fetch_text, force=refresh)
				else:
					created, pages = _ingest_one(ia, item_id, profile_name, fetch_text, refresh=refresh)
					outcome = "created" if created else "updated"
				frappe.db.commit()
				error = None
				break
			except Exception as e:
				frappe.db.rollback()
				error = e
				if not _is_transient(e) or attempt == 2:
					break
				time.sleep(1 + attempt * 2)  # another worker touched the same creator/subject; retry
		# Counters/log go in their own short transaction so parallel batches never conflict.
		if error is None:
			_bump(
				run_name,
				processed=1,
				created_count=int(outcome == "created"),
				updated_count=int(outcome == "updated"),
				skipped_count=int(outcome == "unchanged"),
			)
			if verbose and outcome != "unchanged":
				print(f"{'NEW' if outcome == 'created' else 'UPD'} {item_id} ({pages} pages)")
		elif isinstance(error, BookLimitReached):  # another batch took the last room meanwhile
			_bump(run_name, processed=1, skipped_count=1)
			if not limit_told:
				_log(run_name, f"batch {batch_no}: book limit reached: new books are skipped", verbose)
				limit_told = True
		else:
			_bump(run_name, processed=1, failed_count=1)
			_log(run_name, f"FAIL {item_id}: {str(error)[:300]}", verbose)
		frappe.db.commit()
	_close_batch(run_name, verbose)


def _is_transient(e: Exception) -> bool:
	"""Lock waits, deadlocks, snapshot conflicts and duplicate inserts from parallel workers."""
	text = str(e)
	return (
		frappe.db.is_deadlocked(e)
		or frappe.db.is_timedout(e)
		or any(code in text for code in ("1020", "1205", "1213", "1062"))
		or isinstance(e, frappe.DuplicateEntryError)
	)


def _close_batch(run_name: str, verbose: bool = False) -> None:
	# Row lock so two batches finishing together can't both miss (or both do) the close.
	frappe.db.commit()
	frappe.db.sql(f"select pending_chunks from `{RUN}` where name=%s for update", run_name)
	frappe.db.sql(
		f"update `{RUN}` set pending_chunks = greatest(ifnull(pending_chunks,0) - 1, 0) where name=%s",
		run_name,
	)
	remaining = frappe.db.sql(f"select pending_chunks from `{RUN}` where name=%s", run_name)[0][0]
	frappe.db.commit()
	if remaining == 0:
		_finish(run_name, verbose)


def _finish(run_name: str, verbose: bool = False) -> None:
	row = frappe.db.sql(
		f"select status, created_count, updated_count, skipped_count, failed_count from `{RUN}` where name=%s",
		run_name,
		as_dict=True,
	)[0]
	if row.status == "Paused":
		return  # the last running batch has stopped; the rest waits on the run for Resume
	status = (
		row.status
		if row.status == "Cancelled"
		else ("Completed with Errors" if row.failed_count else "Completed")
	)
	_log(
		run_name,
		f"Done: {row.created_count or 0} new, {row.updated_count or 0} updated, "
		f"{row.skipped_count or 0} skipped, {row.failed_count or 0} failed",
		verbose,
	)
	frappe.db.sql(f"update `{RUN}` set finished_on=%s where name=%s", (now_datetime(), run_name))
	_set_status(run_name, status)
	frappe.db.commit()


def run_ingest(
	run_name: str, verbose: bool = False, limit_override: int | None = None, foreground: bool = True
) -> None:
	"""Command-line entry point: plan, then either process here or hand batches to the workers."""
	batches = plan_run(run_name, limit_override=limit_override, foreground=foreground, verbose=verbose)
	if foreground:
		for n, batch in enumerate(batches, 1):
			run_batch(run_name, batch, n, verbose=verbose)


# -- scheduler --------------------------------------------------------------------------


def _run_scheduled(schedule: str):
	if cint(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest")):
		return  # paused from Background Jobs (or Settings)
	for name in frappe.get_all(
		"RD Ingest Profile", filters={"enabled": 1, "schedule": schedule}, pluck="name"
	):
		running = frappe.db.exists(
			"RD Ingest Run", {"profile": name, "status": ("in", ["Queued", "Running", "Paused"])}
		)
		if running:
			continue
		run = create_run(frappe.get_doc("RD Ingest Profile", name), "Scheduler")
		enqueue_plan(run.name)


def mark_interrupted_runs(idle_hours: int = 2) -> None:
	"""Hourly: a run with no progress for a while lost its workers (restart, crash, reboot)."""
	from frappe.utils import add_to_date

	cutoff = add_to_date(now_datetime(), hours=-idle_hours)
	for name in frappe.get_all(
		"RD Ingest Run", filters={"status": "Running", "modified": ("<", cutoff)}, pluck="name"
	):
		_log(
			name,
			f"No progress for {idle_hours} h, so the workers were probably restarted. "
			"Run the profile again: books already ingested are skipped.",
		)
		frappe.db.sql(f"update `{RUN}` set finished_on=%s where name=%s", (now_datetime(), name))
		_set_status(name, "Interrupted")
	frappe.db.commit()


def run_scheduled_hourly():
	_run_scheduled("Hourly")


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
