"""Search engine adapter (Meilisearch).

Two indexes:
  {prefix}_books  one document per RD Item (metadata + a text excerpt)
  {prefix}_pages  one document per OCR'd page (deep search inside books)

Page text lives only in the search index, never in MariaDB, so the database
stays small as the collection grows. Everything goes through `MeiliClient`, so
swapping to OpenSearch later means writing one new adapter.
"""

from __future__ import annotations

import hashlib
import json
import re

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import item_to_record, settings
from sok_resdesk.core.normalize import decade_of
from sok_resdesk.holding import hold_when_paused

# How far Meilisearch counts a search's results. The portal shows "N books" from this count, so the
# books index counts well past the size of any catalogue (a cap of 10,000 froze the number
# shown at 10,000 however many books came in). Page text has millions of documents, so it
# keeps a small cap and the portal shows "10,000+ matching pages".
BOOKS_MAX_HITS = 1_000_000
PAGES_MAX_HITS = 10_000

BOOK_SETTINGS = {
	"searchableAttributes": [
		"title",
		"alt_title",
		"creators",
		"alt_creators",
		"subjects",
		"series",
		"publisher",
		"description",
		"item_id",
		"text_excerpt",
	],
	"filterableAttributes": [
		"item_id",
		"language",
		"language_label",
		"year",
		"decade",
		"creators",
		"subjects",
		"collections",
		"access_status",
		"has_fulltext",
		"source",
		"visibility",
		"curated",
		"item_type",
	],
	"sortableAttributes": ["year", "title_sort", "indexed_at"],
	"displayedAttributes": ["*"],
	"faceting": {"maxValuesPerFacet": 200, "sortFacetValuesBy": {"*": "count"}},
	"pagination": {"maxTotalHits": BOOKS_MAX_HITS},
}
# Tuned for millions of page documents:
#  - proximityPrecision byAttribute: much smaller index and faster indexing; word
#    proximity is still used, just not at word-by-word precision
#  - searchCutoffMs: a very broad query returns its best hits in bounded time
#  - prefix search stays ON: Kannada words carry suffixes (ಕನಕ → ಕನಕದಾಸರ), so
#    matching word beginnings matters more than the ~7% of disk it would save
#  - page documents carry only text + the fields needed for filtering; titles and
#    authors are looked up from the books index for the 20 hits on screen
PAGE_SETTINGS = {
	"searchableAttributes": ["text"],
	"proximityPrecision": "byAttribute",
	"prefixSearch": "indexingTime",
	"facetSearch": False,
	"searchCutoffMs": 1500,
	"filterableAttributes": [
		"item_id",
		"language_label",
		"year",
		"decade",
		"collections",
		"creators",
		"visibility",
		"curated",
		"item_type",
		"subjects",
	],
	"sortableAttributes": ["leaf"],
	"displayedAttributes": ["*"],
	"pagination": {"maxTotalHits": PAGES_MAX_HITS},
}
FACETS = ["curated", "item_type", "language_label", "decade", "subjects", "creators", "collections"]


class SearchError(Exception):
	pass


def doc_id(item_id: str, suffix: str = "") -> str:
	"""Meilisearch ids allow only [A-Za-z0-9_-]; IA identifiers may contain dots."""
	safe = re.sub(r"[^A-Za-z0-9_-]", "_", item_id)
	if safe != item_id:
		safe += "-" + hashlib.md5(item_id.encode()).hexdigest()[:6]
	return f"{safe}{suffix}"


class MeiliClient:
	def __init__(self, url: str, key: str = "", prefix: str = "rd"):
		self.url = url.rstrip("/")
		self.prefix = prefix or "rd"
		self.session = requests.Session()
		if key:
			self.session.headers["Authorization"] = f"Bearer {key}"

	@classmethod
	def from_settings(cls) -> MeiliClient:
		s = settings()
		url = s.meili_url or frappe.conf.get("resdesk_meili_url") or "http://127.0.0.1:7700"
		key = s.get_password("meili_api_key", raise_exception=False) if s.meili_api_key else None
		key = key or frappe.conf.get("resdesk_meili_key") or ""
		return cls(url, key, s.index_prefix or "rd")

	@property
	def books(self) -> str:
		return f"{self.prefix}_books"

	@property
	def pages(self) -> str:
		return f"{self.prefix}_pages"

	def _req(self, method: str, path: str, **kwargs):
		if "json" in kwargs:
			# Kannada, Hindi, Tamil… as themselves, not \uXXXX escapes: about half the bytes
			# for Meilisearch to read, which is most of what a page-text task sends
			body = kwargs.pop("json")
			kwargs["data"] = json.dumps(body, ensure_ascii=False).encode("utf-8")
			kwargs["headers"] = {**kwargs.get("headers", {}), "Content-Type": "application/json"}
		try:
			resp = self.session.request(method, f"{self.url}{path}", timeout=60, **kwargs)
		except requests.RequestException as exc:
			raise SearchError(_("Cannot reach Meilisearch at {0}: {1}").format(self.url, exc)) from exc
		if resp.status_code >= 400:
			raise SearchError(f"Meilisearch {method} {path}: {resp.status_code} {resp.text[:300]}")
		return resp.json() if resp.content else {}

	def health(self) -> dict:
		return self._req("GET", "/health")

	def wait(self, task: dict, timeout: float = 60.0) -> dict:
		import time

		uid = task.get("taskUid")
		if uid is None:
			return task
		start = time.monotonic()
		while time.monotonic() - start < timeout:
			info = self._req("GET", f"/tasks/{uid}")
			if info.get("status") in ("succeeded", "failed", "canceled"):
				if info.get("status") == "failed":
					raise SearchError(str(info.get("error")))
				return info
			time.sleep(0.3)
		return {"status": "timeout", "taskUid": uid}

	def setup(self) -> None:
		for index, conf in ((self.books, BOOK_SETTINGS), (self.pages, PAGE_SETTINGS)):
			try:
				self.wait(self._req("POST", "/indexes", json={"uid": index, "primaryKey": "id"}))
			except SearchError as e:
				if "index_already_exists" not in str(e):
					raise
			self.wait(self._req("PATCH", f"/indexes/{index}/settings", json=conf), timeout=120)

	def add(self, index: str, documents: list[dict], wait: bool = False) -> dict:
		if not documents:
			return {}
		task = self._req("POST", f"/indexes/{index}/documents", json=documents)
		return self.wait(task) if wait else task

	def delete_by_filter(self, index: str, filter_: str) -> dict:
		return self._req("POST", f"/indexes/{index}/documents/delete", json={"filter": filter_})

	def delete(self, index: str, ids: list[str]) -> dict:
		return self._req("POST", f"/indexes/{index}/documents/delete-batch", json=ids)

	def search(self, index: str, body: dict) -> dict:
		return self._req("POST", f"/indexes/{index}/search", json=body)

	def stats(self) -> dict:
		return self._req("GET", "/stats")


def _quote(value: str) -> str:
	return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


# -- documents ------------------------------------------------------------------


def book_document(record: dict, excerpt: str = "") -> dict:
	title = record.get("alt_title") or record.get("title") or ""
	return {
		"id": doc_id(record["item_id"]),
		"item_id": record["item_id"],
		"title": record.get("title"),
		"alt_title": record.get("alt_title"),
		"title_sort": title.lower()[:100],
		"creators": record.get("creators") or [],
		"alt_creators": [a for a in record.get("alt_creators") or [] if a],
		"year": record.get("year"),
		"decade": record.get("decade") or decade_of(record.get("year")),
		"language": record.get("language"),
		"language_label": record.get("language_label") or "Unknown",
		"publisher": record.get("publisher"),
		"series": record.get("series"),
		"subjects": record.get("subjects") or [],
		"collections": record.get("collections") or [],
		"description": (record.get("description") or "")[:3000],
		"page_count": record.get("page_count"),
		"access_status": record.get("access_status"),
		"has_fulltext": bool(record.get("has_fulltext")),
		"source": record.get("source"),
		"visibility": record.get("visibility") or "Public",
		"curated": record.get("curated_collections") or [],
		"item_type": record.get("item_type") or "Book",
		"thumbnail_url": record.get("thumbnail_url"),
		"text_excerpt": excerpt[:5000],
		"indexed_at": int(now_datetime().timestamp()),
	}


def page_documents(record: dict, pages: list[dict], max_chars: int = 6000) -> list[dict]:
	docs = []
	for page in pages:
		docs.append(
			{
				"id": doc_id(record["item_id"], f"__p{page['leaf']}"),
				"item_id": record["item_id"],
				"leaf": page["leaf"],
				"label": page.get("label") or "",
				"text": page["text"][:max_chars],
				"creators": record.get("creators") or [],
				"year": record.get("year"),
				"decade": record.get("decade") or decade_of(record.get("year")),
				"language_label": record.get("language_label") or "Unknown",
				"collections": record.get("collections") or [],
				"visibility": record.get("visibility") or "Public",
				"curated": record.get("curated_collections") or [],
				"item_type": record.get("item_type") or "Book",
				"subjects": record.get("subjects") or [],
			}
		)
	return docs


# -- indexing -------------------------------------------------------------------


def index_record(
	record: dict,
	pages: list[dict] | None = None,
	client: MeiliClient | None = None,
	replace_pages: bool = True,
) -> int:
	"""Index one book and (optionally) its pages. Returns number of pages indexed."""
	client = client or MeiliClient.from_settings()
	s = settings()
	pages = pages or []
	excerpt = " ".join(p["text"] for p in pages[:6])
	client.add(client.books, [book_document(record, excerpt)])
	count, uid = 0, None
	if pages and cint(s.index_pages):
		if replace_pages:  # new books have no old pages to remove
			client.delete_by_filter(client.pages, f"item_id = {_quote(record['item_id'])}")
		docs = page_documents(record, pages, cint(s.max_page_chars) or 6000)
		for i in range(0, len(docs), 500):
			uid = _task_uid(client.add(client.pages, docs[i : i + 500])) or uid
		count = len(docs)
	frappe.db.set_value(
		"RD Item",
		record["item_id"],
		{
			"indexed_on": now_datetime(),
			**({"indexed_pages": count, "pages_pending": 0, "page_task": uid or 0} if pages else {}),
			**quality_fields(pages),
		},
		update_modified=False,
	)
	return count


def quality_fields(pages: list[dict] | None) -> dict:
	"""OCR quality of a book's pages, as RD Item fields (nothing when it has no page text)."""
	from sok_resdesk.core.ocrquality import book_quality

	q = book_quality(pages or [])
	if q["score"] is None:
		return {}
	return {"ocr_quality": q["score"], "ocr_low_pages": q["low_pages"]}


MAX_WAITING = 300  # search-engine tasks waiting before workers hold back (see wait_for_room)
WAIT_UP_TO = 15 * 60  # seconds a worker holds back at most, then sends anyway


def waiting_tasks(client: MeiliClient) -> int:
	return client._req("GET", "/tasks", params={"statuses": "enqueued", "limit": 1}).get("total", 0)


def wait_for_room(client: MeiliClient, sleep=None) -> int:
	"""Back-pressure: while the search engine has more than MAX_WAITING tasks waiting, the worker
	waits (up to WAIT_UP_TO) instead of adding more. Ingesting then goes at the pace the engine
	can index, rather than piling up a queue it can never get through. Returns seconds waited."""
	import time

	sleep = sleep or time.sleep
	waited = 0
	while waited < WAIT_UP_TO:
		try:
			waiting = waiting_tasks(client)
		except Exception:
			break  # can't tell: carry on; sending reports the real error
		if not isinstance(waiting, int) or waiting <= MAX_WAITING:
			break
		sleep(10)
		waited += 10
	return waited


def engine_status(client: MeiliClient | None = None) -> dict:
	"""What the search engine is doing, for Background Jobs → Machine and the Server page:
	tasks waiting, the batch it is working on (since when, how far), the oldest waiting task,
	and the latest failures with their errors."""
	client = client or MeiliClient.from_settings()
	waiting = client._req("GET", "/tasks", params={"statuses": "enqueued", "limit": 1})
	try:
		oldest = client._req("GET", "/tasks", params={"statuses": "enqueued", "limit": 1, "reverse": "true"})
	except SearchError:
		oldest = {}  # an engine too old for reverse=
	batch = client._req("GET", "/batches", params={"statuses": "processing", "limit": 1}).get("results") or []
	failed = client._req("GET", "/tasks", params={"statuses": "failed", "limit": 3}).get("results") or []
	out = {
		"waiting": waiting.get("total", 0),
		"oldest_waiting": ((oldest.get("results") or [{}])[0]).get("enqueuedAt"),
		"processing": None,
		"failed": [
			{
				"type": t.get("type"),
				"at": t.get("finishedAt"),
				"error": ((t.get("error") or {}).get("message") or "")[:300],
			}
			for t in failed
		],
	}
	if batch:
		b = batch[0]
		stats = b.get("stats") or {}
		out["processing"] = {
			"started": b.get("startedAt"),
			"tasks": stats.get("totalNbTasks"),
			"types": sorted((stats.get("types") or {}).keys()),
			"indexes": sorted((stats.get("indexUids") or {}).keys()),
			"percent": round(((b.get("progress") or {}).get("percentage") or 0), 1),
		}
	return out


class IndexBuffer:
	"""Books (and their page text) waiting to go to Meilisearch, sent together.

	Meilisearch works through its tasks one at a time, whichever index they are for, and only
	merges neighbouring tasks of the same kind. Sending each book's own few tasks (the book,
	the old pages to drop, the new pages) made the page text of earlier books queue in front of
	the next book itself, so the portal's list of books trailed far behind the catalogue.
	Collected here, a batch of books goes as one task for all the books, which readers see at
	once, then one for the old pages and a few big ones for the new pages."""

	PAGE_CHUNK = 2000  # page documents per task

	def __init__(self, client: MeiliClient | None = None, flush_books: int = 10):
		self.client = client
		self.flush_books = flush_books
		self.books: list[dict] = []
		self.stale: list[str] = []  # books whose old pages go before the new ones arrive
		self.pages: list[dict] = []
		self.counts: dict[str, int | None] = {}  # item -> pages indexed (None: no page text sent)
		self.quality: dict[str, dict] = {}  # item -> its OCR quality fields

	def add(self, record: dict, pages: list[dict], replace_pages: bool = True) -> int:
		"""Queue one book (nothing is sent yet: see due and flush). Returns its page count."""
		s = settings()
		excerpt = " ".join(p["text"] for p in pages[:6])
		self.books.append(book_document(record, excerpt))
		docs = []
		if pages and cint(s.index_pages):
			docs = page_documents(record, pages, cint(s.max_page_chars) or 6000)
			if replace_pages:
				self.stale.append(record["item_id"])
			self.pages.extend(docs)
		self.counts[record["item_id"]] = len(docs) if pages else None
		self.quality[record["item_id"]] = quality_fields(pages)
		return len(docs)

	@property
	def due(self) -> bool:
		return len(self.books) >= self.flush_books

	def flush(self) -> None:
		"""Send what is waiting: the books first, so they are listed before their page text is."""
		if not self.books:
			return
		books, stale, pages, counts, quality = self.books, self.stale, self.pages, self.counts, self.quality
		self.books, self.stale, self.pages, self.counts, self.quality = [], [], [], {}, {}
		client = self.client = self.client or MeiliClient.from_settings()
		wait_for_room(client)
		client.add(client.books, books)
		held = pages_held()  # Background Jobs → Search queue → Hold page text
		page_task: dict[str, int] = {}  # item -> the last task carrying its pages
		if not held:
			if stale:
				filters = " OR ".join(f"item_id = {_quote(i)}" for i in stale)
				client.delete_by_filter(client.pages, filters)
			for i in range(0, len(pages), self.PAGE_CHUNK):
				chunk = pages[i : i + self.PAGE_CHUNK]
				uid = _task_uid(client.add(client.pages, chunk))
				if uid is not None:
					for doc in chunk:
						page_task[doc["item_id"]] = uid
		now = now_datetime()
		for item_id, count in counts.items():
			values = {"indexed_on": now} | (quality.get(item_id) or {})
			if count is not None and held:
				values["pages_pending"] = 1  # sent when page text is resumed (search_queue)
			elif count is not None:
				values |= {
					"indexed_pages": count,
					"pages_pending": 0,
					"page_task": page_task.get(item_id) or 0,
				}
			frappe.db.set_value("RD Item", item_id, values, update_modified=False)


def _task_uid(task) -> int | None:
	uid = task.get("taskUid") if isinstance(task, dict) else None
	return uid if isinstance(uid, int) else None


def pages_held() -> bool:
	# read fresh: a worker in the middle of a long run must notice Hold at once
	return bool(frappe.db.get_single_value("RD Settings", "hold_page_text", cache=False))


def index_missing(limit: int = 0) -> list[str]:
	"""Published books that never reached the search engine (indexed_on is empty): a worker
	stopped between saving a book and sending it."""
	return frappe.get_all(
		"RD Item",
		filters={"published": 1, "indexed_on": ("is", "not set")},
		pluck="name",
		order_by="creation asc",
		limit=limit or None,
	)


PAGE_FIELDS = (
	"creators",
	"year",
	"decade",
	"language_label",
	"collections",
	"visibility",
	"curated",
	"item_type",
	"subjects",
)


def update_item_fields(names: list[str], client: MeiliClient | None = None, wait: bool = False) -> None:
	"""Push catalogue edits (metadata, visibility, collections) to both indexes without
	re-indexing page text. Book documents keep their text excerpt; page documents get the
	fields they carry for filtering. Batched: one index task per 500 books / 10,000 pages."""
	client = client or MeiliClient.from_settings()
	names = [n for n in dict.fromkeys(names) if n]
	last = None
	for i in range(0, len(names), 200):
		chunk = frappe.get_all(
			"RD Item", filters={"name": ("in", names[i : i + 200]), "published": 1}, pluck="name"
		)
		if not chunk:
			continue
		books = {}
		for name in chunk:
			doc = book_document(item_to_record(frappe.get_doc("RD Item", name)))
			doc.pop("indexed_at", None)
			books[name] = doc
		flt = f"item_id IN [{', '.join(_quote(n) for n in chunk)}]"
		indexed = {
			d["item_id"]
			for d in client._req(
				"POST",
				f"/indexes/{client.books}/documents/fetch",
				json={"filter": flt, "fields": ["item_id"], "limit": 1000},
			).get("results", [])
		}
		new = [dict(b, text_excerpt="") for n, b in books.items() if n not in indexed]
		if new:
			last = client.add(client.books, new)
		partial = [
			{k: v for k, v in b.items() if k != "text_excerpt"} for n, b in books.items() if n in indexed
		]
		if partial:
			last = client._req("PUT", f"/indexes/{client.books}/documents", json=partial)
		updates, offset = [], 0
		while True:
			res = client._req(
				"POST",
				f"/indexes/{client.pages}/documents/fetch",
				json={"filter": flt, "fields": ["id", "item_id"], "limit": 10000, "offset": offset},
			)
			rows = res.get("results", [])
			for r in rows:
				b = books.get(r["item_id"])
				if b:
					updates.append({"id": r["id"], **{k: b.get(k) for k in PAGE_FIELDS}})
			offset += len(rows)
			if len(updates) >= 10000 or not rows or offset >= res.get("total", 0):
				if updates:
					last = client._req("PUT", f"/indexes/{client.pages}/documents", json=updates)
					updates = []
			if not rows or offset >= res.get("total", 0):
				break
	if wait and last:
		client.wait(last, timeout=120)  # so the next search already sees the change


def remove_record(item_id: str, client: MeiliClient | None = None) -> None:
	client = client or MeiliClient.from_settings()
	client.delete(client.books, [doc_id(item_id)])
	client.delete_by_filter(client.pages, f"item_id = {_quote(item_id)}")


# -- doc_events -----------------------------------------------------------------


def on_item_update(doc, method=None):
	"""Keep the book index in step with manual edits in the Desk."""
	if doc.flags.skip_search_index or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	try:
		client = MeiliClient.from_settings()
		if not doc.published:
			remove_record(doc.item_id, client)
		else:
			update_item_fields([doc.name], client)
	except SearchError as e:
		frappe.log_error("Research Desk: search index update failed", str(e))


def on_item_trash(doc, method=None):
	try:
		remove_record(doc.item_id)
	except SearchError as e:
		frappe.log_error("Research Desk: search index delete failed", str(e))


# -- whitelisted admin actions ------------------------------------------------------


@frappe.whitelist()
def setup_indexes() -> str:
	frappe.only_for(("System Manager", "ResDesk Manager"))
	client = MeiliClient.from_settings()
	try:
		health = client.health()
		client.setup()
		stats = client.stats().get("indexes", {})
	except SearchError as e:
		_set_status(f"Error: {e}")
		frappe.throw(str(e))
	books = stats.get(client.books, {}).get("numberOfDocuments", 0)
	pages = stats.get(client.pages, {}).get("numberOfDocuments", 0)
	msg = _("Connected ({0}). Indexes ready: {1} books, {2} pages.").format(
		health.get("status"), books, pages
	)
	_set_status(msg)
	return msg


def _set_status(msg: str) -> None:
	"""Record the search engine's state in Settings. Right after a migration the workers start
	and write to Settings too; MariaDB then refuses a write from an older snapshot (error 1020),
	so start from a fresh one and try again once."""
	for attempt in range(3):
		try:
			frappe.db.commit()
			frappe.db.set_single_value("RD Settings", "search_status", msg)
			frappe.db.commit()
			return
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt == 2:
				raise
			import time

			time.sleep(1 + attempt)


@frappe.whitelist()
def reindex_item(item_id: str, with_pages: int = 1) -> int:
	frappe.only_for(("System Manager", "ResDesk Manager", "ResDesk Cataloguer"))
	from sok_resdesk.ingest import fetch_pages

	doc = frappe.get_doc("RD Item", item_id)
	record = item_to_record(doc)
	pages = fetch_pages(doc.item_id) if cint(with_pages) and doc.has_page_text else []
	return index_record(record, pages)


@frappe.whitelist()
def enqueue_rebuild(with_pages: int = 1):
	frappe.only_for(("System Manager", "ResDesk Manager"))
	return queue_rebuild(cint(with_pages))


@frappe.whitelist()
def enqueue_index_missing(with_pages: int = 1) -> int:
	"""Send the books that never reached the search engine (a worker stopped, or the engine was
	down) without redoing the ones that did. Returns how many books were queued."""
	frappe.only_for(("System Manager", "ResDesk Manager"))
	return queue_rebuild(cint(with_pages), names=index_missing(), job_prefix="resdesk-index-missing")


def queue_rebuild(
	with_pages: int = 1,
	batch_size: int = 50,
	names: list[str] | None = None,
	job_prefix: str = "resdesk-reindex",
) -> int:
	"""Split a full re-index (or just `names`) into batches that the queue workers run in parallel."""
	frappe.cache.delete_value(
		"resdesk:stop-background"
	)  # a new rebuild overrides an earlier "stop everything"
	MeiliClient.from_settings().setup()
	if names is None:
		names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	for n, i in enumerate(range(0, len(names), batch_size), 1):
		frappe.enqueue(
			"sok_resdesk.search.rebuild_batch",
			queue="long",
			timeout=6 * 3600,
			names=names[i : i + batch_size],
			with_pages=with_pages,
			job_id=f"{job_prefix}-{n}",
		)
	return len(names)


@hold_when_paused("long")
def rebuild_batch(names: list[str], with_pages: int = 1, verbose: bool = False) -> int:
	from sok_resdesk import priority
	from sok_resdesk.ingest import fetch_pages

	buffer = IndexBuffer(MeiliClient.from_settings())
	try:
		return _rebuild(names, with_pages, verbose, buffer, priority, fetch_pages)
	finally:
		buffer.flush()
		frappe.db.commit()


def _rebuild(names, with_pages, verbose, buffer, priority, fetch_pages) -> int:
	for n, name in enumerate(names, 1):
		if frappe.cache.get_value("resdesk:stop-background"):
			break  # "Stop everything" on the Background Jobs page
		frappe.db.commit()
		priority.apply()
		doc = frappe.get_doc("RD Item", name)
		pages = []
		if with_pages and doc.has_page_text:
			try:
				pages = fetch_pages(doc.item_id)  # local cache first, archive.org only if missing
			except Exception as e:  # keep going; one bad item should not stop a rebuild
				frappe.log_error("Research Desk: page fetch failed", f"{name}: {e}")
		buffer.add(item_to_record(doc), pages)
		if buffer.due:
			buffer.flush()
		frappe.db.commit()
		if verbose:
			print(f"[{n}/{len(names)}] {name} ({len(pages)} pages)")
	return len(names)


def rebuild_all(with_pages: int = 1, verbose: bool = False) -> int:
	"""Re-index everything in this process (used by `resdesk reindex`)."""
	frappe.cache.delete_value("resdesk:stop-background")
	client = MeiliClient.from_settings()
	client.setup()
	names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	return rebuild_batch(names, with_pages, verbose)


def reset_pages_index() -> None:
	"""Drop and recreate the pages index (after changing what page documents contain)."""
	client = MeiliClient.from_settings()
	try:
		client.wait(client._req("DELETE", f"/indexes/{client.pages}"), timeout=300)
	except SearchError:
		pass
	client.setup()


# -- public search ----------------------------------------------------------------


def _attach_book_fields(client: MeiliClient, hits: list[dict]) -> None:
	"""Add title/authors to page hits from the (small) books index: one extra query per page of results."""
	ids = list(dict.fromkeys(h["item_id"] for h in hits))
	if not ids:
		return
	books = client.search(
		client.books,
		{
			"q": "",
			"limit": len(ids),
			"filter": f"item_id IN [{', '.join(_quote(i) for i in ids)}]",
			"attributesToRetrieve": ["item_id", "title", "alt_title", "creators"],
		},
	).get("hits", [])
	by_id = {b["item_id"]: b for b in books}
	for h in hits:
		b = by_id.get(h["item_id"], {})
		h.setdefault("title", b.get("title") or h["item_id"])
		h.setdefault("alt_title", b.get("alt_title"))
		h.setdefault("creators", b.get("creators") or [])


def build_filter(filters: dict | None) -> list:
	parts: list = []
	for field, values in (filters or {}).items():
		if field in ("year_from", "year_to"):
			continue
		if field not in FACETS + ["language", "item_id", "access_status"]:  # noqa: RUF005
			continue
		if isinstance(values, str):
			values = [values]
		values = [v for v in values or [] if v not in (None, "")]
		if values:
			parts.append([f"{field} = {_quote(v)}" for v in values])
	if (filters or {}).get("year_from"):
		parts.append(f"year >= {cint(filters['year_from'])}")
	if (filters or {}).get("year_to"):
		parts.append(f"year <= {cint(filters['year_to'])}")
	return parts


def search(
	q: str = "",
	mode: str = "books",
	filters: dict | None = None,
	page: int = 1,
	per_page: int = 20,
	sort: str = "",
	access: dict | None = None,
) -> dict:
	"""access: {"books": filter, "pages": filter} from access.search_filter; None = no limit, "" = nothing."""
	access = access or {}
	if access.get(mode) == "":
		return {
			"hits": [],
			"totalHits": 0,
			"totalPages": 0,
			"page": 1,
			"facetDistribution": {},
			"restricted": True,
		}
	client = MeiliClient.from_settings()
	page, per_page = max(1, cint(page)), min(max(1, cint(per_page)), 100)
	body: dict = {"q": q or "", "page": page, "hitsPerPage": per_page, "filter": build_filter(filters)}
	if access.get(mode):
		body["filter"].append(access[mode])
	if mode == "pages":
		body.update(
			{
				"attributesToCrop": ["text"],
				"cropLength": 40,
				"attributesToHighlight": ["text"],
				"highlightPreTag": "<mark>",
				"highlightPostTag": "</mark>",
				"attributesToRetrieve": ["item_id", "leaf", "label", "year", "language_label", "visibility"],
			}
		)
		result = client.search(client.pages, body)
		_attach_book_fields(client, result.get("hits", []))
		# facet counts always come from the books index so the sidebar stays useful
		book_filter = build_filter(filters) + ([access["books"]] if access.get("books") else [])
		facets = client.search(client.books, {"q": "", "limit": 0, "facets": FACETS, "filter": book_filter})
		result["facetDistribution"] = facets.get("facetDistribution", {})
	else:
		body.update(
			{
				"facets": FACETS,
				"attributesToCrop": ["description", "text_excerpt"],
				"cropLength": 30,
				"attributesToHighlight": ["title", "alt_title", "creators", "description", "text_excerpt"],
				"highlightPreTag": "<mark>",
				"highlightPostTag": "</mark>",
			}
		)
		if sort in ("year:asc", "year:desc", "title_sort:asc"):
			body["sort"] = [sort]
		result = client.search(client.books, body)
	return result
