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
import random
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
TRIES = 5  # attempts per book when parallel workers get in each other's way
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
	with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=3) as f:
		json.dump(pages, f, ensure_ascii=False)
	os.replace(tmp, path)


def fetch_pages(
	item_id: str, ia: IAClient | None = None, page_numbers: dict | None = None, refresh: bool = False
) -> list[dict]:
	"""Page texts for one book, as readers should see them: archive.org's (or the folder's) text,
	with the pages that were re-read or corrected replaced by their current version (pagetext.py)."""
	from sok_resdesk.pagetext import apply

	return apply(item_id, _source_pages(item_id, ia, page_numbers, refresh))


def _source_pages(
	item_id: str, ia: IAClient | None = None, page_numbers: dict | None = None, refresh: bool = False
) -> list[dict]:
	"""Page texts as the source has them: local cache first, then the Internet Archive."""
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
	ia: IAClient,
	item_id: str,
	profile: str | None,
	fetch_text: bool,
	refresh: bool = False,
	buffer=None,
) -> tuple[bool, int]:
	"""Fetch, store and index one item (or hand it to the batch's IndexBuffer, which sends a
	whole batch at once). Returns (created, pages_indexed)."""
	from sok_resdesk.search import SearchError, index_record

	data = ia.metadata(item_id)
	meta, files = data.get("metadata", {}), data.get("files", [])
	record = normalize_ia_item(item_id, meta, files)
	name, created = upsert_item(record, raw=meta, profile=profile)

	pages: list[dict] = []
	if fetch_text and record["has_page_text"]:
		pages = fetch_pages(item_id, ia, data.get("page_numbers"), refresh=refresh)
	try:
		record = item_to_record(frappe.get_doc("RD Item", name))
		if buffer is not None:
			return created, buffer.add(record, pages, replace_pages=not created)
		count = index_record(record, pages, replace_pages=not created)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return created, count


# -- runs -----------------------------------------------------------------------------------


def create_run(profile_doc, triggered_by: str = "Manual"):
	# one run per profile at a time: two would fetch the same books twice
	active = frappe.db.get_value(
		"RD Ingest Run",
		{"profile": profile_doc.name, "status": ("in", ["Queued", "Running", "Paused"])},
		"name",
	)
	if active:
		frappe.throw(
			frappe._(
				"Run {0} of this profile is still going (or paused). Let it finish, Resume it, or stop it first: two runs would fetch the same books twice."
			).format(active),
			title=frappe._("Already running"),
		)
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
	carried_on_from = run.started_on  # set when this run is listed again (Carry On / Try Again)
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
		from sok_resdesk import ia_sync

		if ia_sync.is_sync_run(run, profile):
			# only what changed on archive.org since the last run (new, changed, back again)
			ids = ia_sync.plan(run_name, profile, ia, lambda m: _log(run_name, m, verbose))
			only_new = False
		elif profile.is_folder:
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
		if carried_on_from and ids:
			# listed again: books this run (or any other) already did since it started are not redone
			done = _done_since([_entry_id(e) for e in ids], carried_on_from)
			if done:
				ids = [e for e in ids if _entry_id(e) not in done]
				skipped += len(done)
				_log(run_name, f"{len(done):,} books were already done since this run started", verbose)

		size = max(1, cint(settings().get("batch_size")) or 50)
		batches = [ids[i : i + size] for i in range(0, len(ids), size)]
		frappe.db.sql(
			f"update `{RUN}` set total_found=%s, skipped_count=%s, processed=%s, chunks_total=%s, pending_chunks=%s, "
			"limit_skipped=0, waiting_work=null "
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
			# Batches wait on the run and go into the queue a few at a time (see _feed): queueing
			# hundreds at once fills the queue ("Too many queued background jobs") and holds up
			# every other job and run.
			frappe.db.sql(
				f"update `{RUN}` set waiting_work=%s where name=%s",
				(json.dumps({"batches": batches, "next_no": 1}), run_name),
			)
			frappe.db.commit()
			_feed(run_name)
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


WINDOW_MIN, WINDOW_MAX = 4, 40  # batches of one run in the queue at a time


def _window() -> int:
	"""Twice the workers on the long queue, so they never wait, within WINDOW_MIN..WINDOW_MAX."""
	try:
		from frappe.utils.background_jobs import get_redis_conn
		from rq import Worker

		workers = sum(
			1
			for w in Worker.all(connection=get_redis_conn())
			if any(q.name.rsplit(":", 1)[-1] == "long" for q in w.queues)
		)
	except Exception:
		workers = 0
	return min(WINDOW_MAX, max(WINDOW_MIN, 2 * workers))


def _read_waiting(raw) -> dict:
	try:
		w = json.loads(raw) if raw else {}
	except ValueError:
		w = {}
	return {"batches": w.get("batches") or [], "next_no": cint(w.get("next_no")) or 1}


def waiting_batches(run_name: str) -> list:
	return _read_waiting(frappe.db.get_value("RD Ingest Run", run_name, "waiting_work"))["batches"]


def add_waiting(run_name: str, batches: list, next_no: int = 0) -> None:
	"""Put batches in line on the run; next_no: the lowest number for the next one queued."""
	row = frappe.db.sql(f"select waiting_work from `{RUN}` where name=%s for update", run_name)[0][0]
	w = _read_waiting(row)
	w["batches"] += batches
	w["next_no"] = max(w["next_no"], cint(next_no))
	frappe.db.sql(f"update `{RUN}` set waiting_work=%s where name=%s", (json.dumps(w), run_name))


def take_waiting(run_name: str) -> list:
	"""Take every waiting batch off the run (Pause keeps them as held books)."""
	row = frappe.db.sql(f"select waiting_work from `{RUN}` where name=%s for update", run_name)[0][0]
	w = _read_waiting(row)
	if w["batches"]:
		frappe.db.sql(
			f"update `{RUN}` set waiting_work=%s where name=%s",
			(json.dumps({"batches": [], "next_no": w["next_no"]}), run_name),
		)
	return w["batches"]


def _feed(run_name: str, n: int | None = None) -> int:
	"""Queue up to n (default: the window) of the run's waiting batches. Returns how many."""
	n = _window() if n is None else n
	frappe.db.commit()
	row = frappe.db.sql(
		f"select status, waiting_work from `{RUN}` where name=%s for update", run_name, as_dict=True
	)
	if not row or row[0].status not in ("Queued", "Running") or n <= 0:
		frappe.db.commit()
		return 0
	w = _read_waiting(row[0].waiting_work)
	sent = 0
	for batch in w["batches"][:n]:
		try:
			frappe.enqueue(
				"sok_resdesk.ingest.run_batch",
				queue="long",
				timeout=JOB_TIMEOUT,
				run_name=run_name,
				item_ids=batch,
				batch_no=w["next_no"] + sent,
				job_id=f"resdesk-{run_name}-{w['next_no'] + sent}",
			)
		except Exception as e:  # the queue is full of other work: the rest waits for the next turn
			_log(run_name, f"queue busy, batches wait for the next turn: {str(e)[:200]}")
			break
		sent += 1
	if sent:
		w = {"batches": w["batches"][sent:], "next_no": w["next_no"] + sent}
		frappe.db.sql(f"update `{RUN}` set waiting_work=%s where name=%s", (json.dumps(w), run_name))
	frappe.db.commit()
	return sent


def _entry_id(entry) -> str:
	return entry[0] if isinstance(entry, (list, tuple)) else entry


def _done_since(item_ids: list[str], since) -> set[str]:
	"""Books ingested (by any run) at or after `since`."""
	done: set[str] = set()
	for i in range(0, len(item_ids), 1000):
		done.update(
			frappe.get_all(
				"RD Item",
				filters={"name": ("in", item_ids[i : i + 1000]), "last_ingested": (">=", since)},
				pluck="name",
			)
		)
	return done


def _already_done(item_id: str, since, only_new: bool) -> bool:
	"""Another run (or an earlier try of this one) has already brought this book in, so it
	isn't fetched again: it was ingested after this run started, or it is in the catalogue
	and this run only takes new books."""
	row = frappe.db.sql("select last_ingested from `tabRD Item` where name=%s", item_id)
	if not row:
		return False
	return only_new or bool(since and row[0][0] and row[0][0] >= since)


def run_batch(run_name: str, item_ids: list, batch_no: int = 0, verbose: bool = False) -> None:
	"""Ingest one batch. Items are IA identifiers, or [identifier, folder] pairs for folder
	sources. Safe to run many at once."""
	from sok_resdesk import ia_sync, priority
	from sok_resdesk.search import IndexBuffer

	run = frappe.db.get_value(
		"RD Ingest Run", run_name, ["profile", "started_on", "triggered_by"], as_dict=True
	)
	profile_name = run.profile
	profile = frappe.get_doc("RD Ingest Profile", profile_name)
	fetch_text = bool(cint(profile.fetch_fulltext))
	refresh = bool(cint(profile.update_existing))
	# same rule as plan_run: books already in the catalogue are only fetched again when asked
	only_new = (
		not profile.is_folder
		and not ia_sync.is_sync_run(run, profile)
		and (run.triggered_by == "Scheduler" or not refresh)
	)
	already = 0
	ia = client()
	store = None
	if profile.is_folder:
		from sok_resdesk.local_source import ingest_local_one, open_profile_store

		store = open_profile_store(profile)
	from sok_resdesk.capacity import BookLimitReached, has_room

	limit_told = False
	# books and their page text go to the search engine together, a few books at a time
	buffer = IndexBuffer()
	try:
		for pos, entry in enumerate(item_ids):
			item_id, loc = (entry[0], entry[1]) if isinstance(entry, (list, tuple)) else (entry, None)
			frappe.db.commit()  # start each item with a fresh snapshot
			priority.apply()  # the worker priority chosen in the Desk (Background Jobs → Machine)
			status = _status(run_name)
			if status == "Cancelled":
				_log(run_name, f"batch {batch_no}: cancelled", verbose)
				break
			if status == "Paused" and _paused_here(run_name, item_ids[pos:], batch_no, verbose):
				break
			if _already_done(item_id, run.started_on, only_new):
				already += 1
				_bump(run_name, processed=1, skipped_count=1)
				frappe.db.commit()
				continue
			# at the book limit, books already in the catalogue are still updated; new ones wait
			if not frappe.db.exists("RD Item", item_id) and not has_room():
				if not limit_told:
					_log(run_name, f"batch {batch_no}: book limit reached: new books are skipped", verbose)
					limit_told = True
				_bump(run_name, processed=1, skipped_count=1, limit_skipped=1)
				frappe.db.commit()
				continue
			error = None
			for attempt in range(TRIES):
				try:
					if store is not None:
						outcome, pages = ingest_local_one(
							store, item_id, loc, profile, fetch_text, force=refresh, buffer=buffer
						)
					else:
						created, pages = _ingest_one(
							ia, item_id, profile_name, fetch_text, refresh=refresh, buffer=buffer
						)
						outcome = "created" if created else "updated"
					frappe.db.commit()
					error = None
					break
				except Exception as e:
					frappe.db.rollback()
					error = e
					if not _is_transient(e) or attempt == TRIES - 1:
						break
					# another worker touched the same creator, subject or collection: wait and retry
					time.sleep(1 + attempt * 2 + random.random() * 2)
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
				_bump(run_name, processed=1, skipped_count=1, limit_skipped=1)
				if not limit_told:
					_log(run_name, f"batch {batch_no}: book limit reached: new books are skipped", verbose)
					limit_told = True
			else:
				_bump(run_name, processed=1, failed_count=1)
				_log(run_name, f"FAIL {item_id}: {str(error)[:300]}", verbose)
				# kept on the run so Retry Failed can take exactly these books again
				frappe.db.sql(
					f"update `{RUN}` set failed_items = concat(ifnull(failed_items, ''), %s) where name=%s",
					(json.dumps(entry) + "\n", run_name),
				)
			frappe.db.commit()
			if buffer.due:
				_flush_index(buffer, run_name, batch_no, verbose)
	finally:
		_flush_index(buffer, run_name, batch_no, verbose)
	if already:
		_log(
			run_name,
			f"batch {batch_no}: {already} books already done by another run (or earlier in this one), skipped",
			verbose,
		)
		frappe.db.commit()
	_close_batch(run_name, verbose)


def _flush_index(buffer, run_name: str, batch_no: int, verbose: bool = False) -> None:
	"""Send the batch's waiting books to the search engine. If it can't be reached the books are
	still in the catalogue, and Settings → Search → Index Missing Books sends them later."""
	from sok_resdesk.search import SearchError

	try:
		buffer.flush()
		frappe.db.commit()
	except SearchError as e:
		frappe.db.rollback()
		frappe.log_error("Research Desk: indexing failed", f"run {run_name}, batch {batch_no}: {e}")
		_log(
			run_name, f"batch {batch_no}: the search engine did not take some books: {str(e)[:200]}", verbose
		)
		frappe.db.commit()


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
	else:
		_feed(run_name, 1)  # the next waiting batch takes this one's place in the queue


def _finish(run_name: str, verbose: bool = False) -> None:
	row = frappe.db.sql(
		f"select status, created_count, updated_count, skipped_count, failed_count, limit_skipped from `{RUN}` where name=%s",
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
	if row.limit_skipped:
		_log(
			run_name,
			f"BOOK LIMIT: {row.limit_skipped:,} new books were left out because the book limit is reached. "
			"Raise it in Settings → Machine Resources → Book Limit (or free disk space / give Docker more "
			"memory), then Carry On on this run to bring them in.",
			verbose,
		)
	frappe.db.sql(f"update `{RUN}` set finished_on=%s where name=%s", (now_datetime(), run_name))
	_set_status(run_name, status)
	frappe.db.commit()
	try:
		from sok_resdesk.ia_sync import after_run

		after_run(run_name)  # "in step up to", and the profile's portal collection
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Research Desk: updating after run {run_name} failed")


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


AUTO_CARRY_ON = 3  # times a run whose batches vanished is carried on by itself
AUTO_RETRY = 2  # times a run that ended with failed books (or failed to list them) tries again by itself
RETRY_AFTER_MINUTES = 15  # how long after it ended: a short outage at archive.org is over by then
LOST_MINUTES = 15


def _runs_with_work() -> set[str]:
	"""Runs that still have a job queued, running or held (Pause All / Hold)."""
	from frappe.utils.background_jobs import get_queues, get_redis_conn
	from rq.registry import StartedJobRegistry

	from sok_resdesk.holding import held_jobs
	from sok_resdesk.jobs import _rq_jobs

	# a job whose worker was killed stays "started" until its heartbeat runs out: move those to
	# the failed jobs (where Carry On finds and requeues them) before looking
	for queue in get_queues(connection=get_redis_conn()):
		StartedJobRegistry(queue=queue).cleanup()
	live = {j["run"] for j in _rq_jobs() if j.get("run")}
	live.update((h.get("kwargs") or {}).get("run_name") for h in held_jobs())
	return live


def mark_interrupted_runs(idle_hours: int = 2, lost_minutes: int = LOST_MINUTES) -> None:
	"""Every 10 minutes: find runs that lost their workers (restart, upgrade, crash, reboot).

	* A run none of whose batches is queued, running or held any more, with no progress for
	  `lost_minutes`, lost them in a restart: it is marked Interrupted and carried on by itself
	  (up to AUTO_CARRY_ON times), skipping the books already done.
	* A run with no progress for `idle_hours` is marked Interrupted (Carry On picks it up).
	"""
	from frappe.utils import add_to_date

	from sok_resdesk.holding import is_paused

	now = now_datetime()
	lost: list[str] = []
	if not is_paused():
		try:
			live = _runs_with_work()
		except Exception:
			live = None  # the queue isn't reachable: decide nothing from it
		if live is not None:
			cutoff = add_to_date(now, minutes=-lost_minutes)
			lost = [
				n
				for n in frappe.get_all(
					"RD Ingest Run",
					filters={"status": ("in", ["Queued", "Running"]), "modified": ("<", cutoff)},
					pluck="name",
				)
				if n not in live
			]
	for name in list(lost):
		row = frappe.db.get_value("RD Ingest Run", name, ["pending_chunks", "waiting_work"], as_dict=True)
		waiting = _read_waiting(row.waiting_work)["batches"]
		if waiting and cint(row.pending_chunks) == len(waiting) and _feed(name):
			lost.remove(name)  # nothing was lost: its next batches just hadn't been queued yet
	for name in lost:
		_log(
			name,
			"Its batches are no longer in the queue: the workers were restarted (an upgrade, a restart or not enough memory).",
		)
		frappe.db.sql(f"update `{RUN}` set finished_on=%s where name=%s", (now, name))
		_set_status(name, "Interrupted")
		frappe.db.commit()
		log = frappe.db.get_value("RD Ingest Run", name, "log") or ""
		if log.count("Carried on by itself") < AUTO_CARRY_ON:
			from sok_resdesk.jobs import retry_run

			try:
				_log(name, "Carried on by itself; books already done are skipped.")
				frappe.db.commit()
				retry_run(name)
			except Exception:
				frappe.db.rollback()
				frappe.log_error(title=f"Research Desk: carrying on run {name} failed")

	if not is_paused():
		_retry_failed_runs(now, add_to_date)

	cutoff = add_to_date(now, hours=-idle_hours)
	for name in frappe.get_all(
		"RD Ingest Run", filters={"status": "Running", "modified": ("<", cutoff)}, pluck="name"
	):
		_log(
			name,
			f"No progress for {idle_hours} h, so the workers were probably restarted. "
			"Retry on this run carries on where it stopped.",
		)
		frappe.db.sql(f"update `{RUN}` set finished_on=%s where name=%s", (now, name))
		_set_status(name, "Interrupted")
	frappe.db.commit()


def _retry_failed_runs(now, add_to_date) -> None:
	"""Runs that ended with failed books, or failed while listing them, try again by themselves
	(AUTO_RETRY times, RETRY_AFTER_MINUTES after they ended): most failures are a busy moment at
	archive.org, a lock between two workers or a restart. After that they wait for Retry."""
	from sok_resdesk.jobs import retry_run

	cutoff = add_to_date(now, minutes=-RETRY_AFTER_MINUTES)
	for name in frappe.get_all(
		"RD Ingest Run",
		filters={"status": ("in", ["Completed with Errors", "Failed"]), "finished_on": ("<", cutoff)},
		pluck="name",
	):
		log = frappe.db.get_value("RD Ingest Run", name, "log") or ""
		if log.count("Retried by itself") >= AUTO_RETRY:
			continue
		try:
			retry_run(name)
			_log(
				name, "Retried by itself (the failed books were taken again; those already done are skipped)."
			)
			frappe.db.commit()
		except Exception:
			# e.g. another run of the profile is going: it stays as it is and the next turn tries again
			frappe.db.rollback()


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
