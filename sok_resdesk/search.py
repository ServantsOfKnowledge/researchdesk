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

from sok_resdesk import features
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
		"note_entity_names",
		"note_tags",
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
		"note_tags",
		"note_entities",
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
		start, pause = time.monotonic(), 0.2
		while time.monotonic() - start < timeout:
			info = self._req("GET", f"/tasks/{uid}")
			if info.get("status") in ("succeeded", "failed", "canceled"):
				if info.get("status") == "failed":
					raise SearchError(str(info.get("error")))
				return info
			time.sleep(pause)
			# a quick task answers at once; a long one isn't asked three times a second
			pause = min(pause * 1.5, 2.0)
		return {"status": "timeout", "taskUid": uid}

	def setup(self) -> None:
		"""Make sure both indexes exist with Research Desk's settings. Only what differs is sent:
		every settings change is a task the engine runs on its own, between the books and pages
		around it, and may make it index everything again, so sending them all whenever an
		ingest run started (or the site migrated) kept the engine busy for nothing."""
		for index, conf in ((self.books, BOOK_SETTINGS), (self.pages, PAGE_SETTINGS)):
			key = f"resdesk:meili-settings:{self.url}:{index}"
			try:
				self._req("GET", f"/indexes/{index}")
			except SearchError as e:
				if " 404 " not in str(e):
					raise
				self.wait(self._req("POST", "/indexes", json={"uid": index, "primaryKey": "id"}))
				frappe.cache.delete_value(key)
			fingerprint = hashlib.sha1(json.dumps(conf, sort_keys=True).encode()).hexdigest()
			if frappe.cache.get_value(key) == fingerprint:
				continue
			changed = settings_diff(conf, self._req("GET", f"/indexes/{index}/settings"))
			if changed:
				self.wait(self._req("PATCH", f"/indexes/{index}/settings", json=changed), timeout=120)
			frappe.cache.set_value(key, fingerprint, expires_in_sec=86400)

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


# the settings whose lists are sets: the engine may give them back in another order
_UNORDERED = {"filterableAttributes", "sortableAttributes", "displayedAttributes"}


def settings_diff(wanted: dict, current: dict) -> dict:
	"""The part of `wanted` that the index's `current` settings don't already have."""

	def same(key, a, b) -> bool:
		if isinstance(a, dict) and isinstance(b, dict):
			return all(k in b and same(k, v, b[k]) for k, v in a.items())
		if isinstance(a, list) and isinstance(b, list) and key in _UNORDERED:
			return sorted(map(str, a)) == sorted(map(str, b))
		return a == b

	return {k: v for k, v in wanted.items() if k not in (current or {}) or not same(k, v, current[k])}


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
		# readers' public notes: their tags and the Wikidata items they say the pages are about
		"note_tags": record.get("note_tags") or [],
		"note_entities": record.get("note_entities") or [],
		"note_entity_names": record.get("note_entity_names") or [],
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
	count, uid, docs = 0, None, []
	if pages and cint(s.index_pages) and features.on("page_search"):
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
			**(
				{
					"indexed_pages": count,
					"pages_pending": 0,
					"page_task": uid or 0,
					"page_text_hash": page_text_hash(docs) if count else "",
				}
				if pages
				else {}
			),
			**quality_fields(pages),
		},
		update_modified=False,
	)
	return count


def page_text_hash(docs: list[dict]) -> str:
	"""A fingerprint of a book's page text as sent to the engine (what is on each page, not the
	book's fields the pages carry): the same text need not be indexed again."""
	h = hashlib.sha1()
	for d in docs:
		h.update(f"{d['leaf']}\x1f{d.get('label') or ''}\x1f{d['text']}\x1e".encode())
	return h.hexdigest()


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
	FLUSH_BOOKS = 25  # books per send: fewer, bigger tasks are less work for the engine than many small

	def __init__(self, client: MeiliClient | None = None, flush_books: int = FLUSH_BOOKS):
		self.client = client
		self.flush_books = flush_books
		self.books: list[dict] = []
		self.stale: list[str] = []  # books whose old pages go before the new ones arrive
		self.pages: list[dict] = []
		self.counts: dict[str, int | None] = {}  # item -> pages indexed (None: no page text sent)
		self.quality: dict[str, dict] = {}  # item -> its OCR quality fields
		self.hashes: dict[str, str] = {}  # item -> fingerprint of the page text sent
		self.same_text: list[str] = []  # books whose page text the engine already has

	def add(
		self, record: dict, pages: list[dict], replace_pages: bool = True, if_changed: bool = False
	) -> int:
		"""Queue one book (nothing is sent yet: see due and flush). Returns its page count.

		if_changed: a book already in the catalogue, fetched again (an update, a sync with
		archive.org). When its page text is what the engine already holds, only the book record
		goes, and its pages get just the fields that changed: re-sending a few hundred pages
		unchanged is most of what indexing costs."""
		s = settings()
		excerpt = " ".join(p["text"] for p in pages[:6])
		self.books.append(book_document(record, excerpt))
		docs = []
		if pages and cint(s.index_pages) and features.on("page_search"):
			docs = page_documents(record, pages, cint(s.max_page_chars) or 6000)
			fingerprint = page_text_hash(docs)
			if replace_pages and if_changed and self._already_sent(record["item_id"], fingerprint, len(docs)):
				self.same_text.append(record["item_id"])
				self.counts[record["item_id"]] = None
				self.quality[record["item_id"]] = quality_fields(pages)
				return len(docs)
			if replace_pages:
				self.stale.append(record["item_id"])
			self.pages.extend(docs)
			self.hashes[record["item_id"]] = fingerprint
		self.counts[record["item_id"]] = len(docs) if pages else None
		self.quality[record["item_id"]] = quality_fields(pages)
		return len(docs)

	@staticmethod
	def _already_sent(item_id: str, fingerprint: str, count: int) -> bool:
		held = frappe.db.get_value(
			"RD Item", item_id, ["page_text_hash", "indexed_pages", "pages_pending"], as_dict=True
		)
		return bool(
			held
			and held.page_text_hash == fingerprint
			and cint(held.indexed_pages) == count
			and not cint(held.pages_pending)
		)

	@property
	def due(self) -> bool:
		return len(self.books) >= self.flush_books

	def flush(self) -> None:
		"""Send what is waiting: the books first, so they are listed before their page text is."""
		if not self.books:
			return
		books, stale, pages, counts, quality = self.books, self.stale, self.pages, self.counts, self.quality
		hashes, same_text = self.hashes, self.same_text
		self.books, self.stale, self.pages, self.counts, self.quality = [], [], [], {}, {}
		self.hashes, self.same_text = {}, []
		client = self.client = self.client or MeiliClient.from_settings()
		wait_for_room(client)
		if same_text:  # before the new book records go, while the engine's copies are the old ones
			_refresh_page_fields(client, {b["item_id"]: b for b in books if b["item_id"] in same_text})
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
					"page_text_hash": hashes.get(item_id, ""),
				}
			frappe.db.set_value("RD Item", item_id, values, update_modified=False)


def _refresh_page_fields(client: MeiliClient, books: dict[str, dict]) -> None:
	"""Give the pages of `books` (item -> new book document) the fields that changed, for the books
	where one did."""
	if not books:
		return
	flt = f"item_id IN [{', '.join(_quote(n) for n in books)}]"
	held = {
		d["item_id"]: d
		for d in client._req(
			"POST",
			f"/indexes/{client.books}/documents/fetch",
			json={"filter": flt, "fields": ["item_id", *PAGE_FIELDS], "limit": 1000},
		).get("results", [])
	}
	repage = [n for n, b in books.items() if not same_fields(b, held.get(n) or {}, PAGE_FIELDS)]
	if repage:
		_update_page_fields(client, repage, books)


def _task_uid(task) -> int | None:
	uid = task.get("taskUid") if isinstance(task, dict) else None
	return uid if isinstance(uid, int) else None


def pages_held() -> bool:
	# read fresh: a worker in the middle of a long run must notice Hold at once
	return bool(frappe.db.get_single_value("RD Settings", "hold_page_text", cache=False))


def reindex_pages(item_id: str, pages: list[dict], client: MeiliClient | None = None) -> int:
	"""Send some pages of a book again (a corrected page): replaces those page documents only."""
	from sok_resdesk.catalogue import item_to_record

	if not pages or not cint(settings().index_pages) or not features.on("page_search"):
		return 0
	client = client or MeiliClient.from_settings()
	record = item_to_record(frappe.get_doc("RD Item", item_id))
	docs = page_documents(record, pages, cint(settings().max_page_chars) or 6000)
	client.add(client.pages, docs)
	return len(docs)


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
	fields they carry for filtering. Batched: one index task per 200 books / 10,000 pages.

	Only what changed is sent: a book whose search record is the same as the one the engine
	holds is left alone, and its pages are rewritten only when a field they carry changed. Most
	saves (an internal note, a review flag answered, an identifier added) change nothing the
	engine keeps, and each rewrite of a book's few hundred pages is real indexing work."""
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
			doc.pop("text_excerpt", None)
			books[name] = doc
		flt = f"item_id IN [{', '.join(_quote(n) for n in chunk)}]"
		indexed = {
			d["item_id"]: d
			for d in client._req(
				"POST",
				f"/indexes/{client.books}/documents/fetch",
				json={"filter": flt, "fields": list(next(iter(books.values()))), "limit": 1000},
			).get("results", [])
		}
		new = [dict(b, text_excerpt="") for n, b in books.items() if n not in indexed]
		if new:
			last = client.add(client.books, new)
		changed = [b for n, b in books.items() if n in indexed and not same_fields(b, indexed[n], b)]
		if changed:
			last = client._req("PUT", f"/indexes/{client.books}/documents", json=changed)
		# pages carry some of the book's fields (for filtering): only books where one of those changed
		repage = [n for n, b in books.items() if n in indexed and not same_fields(b, indexed[n], PAGE_FIELDS)]
		if repage:
			last = _update_page_fields(client, repage, books) or last
	if wait and last:
		client.wait(last, timeout=120)  # so the next search already sees the change


def same_fields(new: dict, held: dict, fields) -> bool:
	"""Whether the engine's copy `held` already has `new`'s values for `fields` (None, missing and
	an empty list count as the same: the engine leaves out what was sent empty)."""

	def norm(v):
		return None if v in (None, "", []) else v

	return all(norm(new.get(f)) == norm(held.get(f)) for f in fields)


def _update_page_fields(client: MeiliClient, names: list[str], books: dict[str, dict]):
	flt = f"item_id IN [{', '.join(_quote(n) for n in names)}]"
	updates, offset, last = [], 0, None
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
	return last


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
	frappe.db.sql("update `tabRD Item` set page_text_hash = '' where ifnull(page_text_hash, '') != ''")
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
		if field not in FACETS + ["language", "item_id", "access_status", "note_tags", "note_entities"]:  # noqa: RUF005
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
		queries, also = expand_query(q, filters, client) if q else ([q or ""], [])
		if len(queries) > 1:
			result = federated(client, client.pages, queries, body, page, per_page)
		else:
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
		queries, also = expand_query(q, filters, client) if q else ([q or ""], [])
		if len(queries) > 1:
			result = federated(client, client.books, queries, body, page, per_page, facets=FACETS)
		else:
			result = client.search(client.books, body)
	result["also"] = also
	return result


# -- romanised words, OR, phrases ------------------------------------------------------------------
# A query typed in Latin letters ("kanakadasa", "vachana") also searches the Indic spellings the
# catalogue really holds (core/translit.py lists the likely ones; a quick probe of the books
# index keeps those that occur, cached a week). "a OR b" searches either. Phrases in "double
# quotes" and -words to leave out are Meilisearch's own. All the queries run as one federated
# search: one list, best matches first, each book once.

OR_SPLIT = re.compile(r"\s+(?:OR|\|)\s+")
TOKEN = re.compile(r'-?"[^"]*"|\S+')
SPELLING_TTL = 7 * 86400
MAX_WORDS = 4
MAX_SCRIPTS = 2


def romanised_on() -> bool:
	"""Settings → Search Engine → Find Indic Spellings (on unless switched off)."""
	value = settings().get("search_romanised")
	return True if value is None else bool(cint(value))


def catalogue_scripts(client: MeiliClient | None = None) -> list[str]:
	"""The Indic scripts of the catalogue's languages, the most common first (cached a day)."""
	from sok_resdesk.core.translit import script_of_language

	client = client or MeiliClient.from_settings()
	key = f"resdesk:catalogue-scripts:{client.books}"
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached
	facets = client.search(client.books, {"q": "", "limit": 0, "facets": ["language_label"]})
	counts: dict[str, int] = {}
	for label, n in (facets.get("facetDistribution", {}).get("language_label") or {}).items():
		script = script_of_language(label)
		if script:
			counts[script] = counts.get(script, 0) + n
	out = sorted(counts, key=counts.get, reverse=True)
	frappe.cache.set_value(key, out, expires_in_sec=86400)
	return out


def _probe(client: MeiliClient, words: list[tuple[str, str]]) -> dict[tuple[str, str], list[str]]:
	"""{(word, script): spellings the books index holds, the most used first}. Each candidate is
	asked twice in one request: as a whole word (a trailing space turns prefix matching off) and
	as the start of a word (Kannada words carry suffixes: ಕನಕದಾಸ → ಕನಕದಾಸರ). A spelling counts only
	with no typo; a start shorter than three letters is too loose to count."""
	from sok_resdesk.core.translit import candidates

	found: dict[tuple[str, str], list[str]] = {}
	todo = []
	for word, script in words:
		cached = frappe.cache.get_value(f"resdesk:spelling:{client.books}:{script}:{word}")
		if cached is not None:
			found[(word, script)] = cached
		else:
			todo.append((word, script))
	for start, stop in ((0, 12), (12, 36)):  # the likely spellings first; more only when none is found
		ask = []
		for word, script in todo:
			if found.get((word, script)):
				continue
			for cand in candidates(word, script, limit=stop)[start:]:
				ask.append((word, script, cand, True))
				ask.append((word, script, cand, False))
		if not ask:
			break
		body = {
			"queries": [
				{
					"indexUid": client.books,
					"q": cand + (" " if whole else ""),
					"limit": 1,
					"showRankingScoreDetails": True,
					"attributesToRetrieve": ["id"],
				}
				for _w, _s, cand, whole in ask
			]
		}
		results = client._req("POST", "/multi-search", json=body).get("results", [])
		whole_hits: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
		start_hits: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
		for n, ((word, script, cand, whole), res) in enumerate(zip(ask, results, strict=False)):
			hits = res.get("hits") or []
			if not hits:
				continue
			typos = ((hits[0].get("_rankingScoreDetails") or {}).get("typo") or {}).get("typoCount", 1)
			if typos:
				continue
			if not whole and len(cand) < 3:
				continue
			bucket = whole_hits if whole else start_hits
			bucket.setdefault((word, script), []).append((-res.get("estimatedTotalHits", 0), n, cand))
		for key in {(w, s) for w, s, _c, _x in ask}:
			ranked = sorted(whole_hits.get(key) or start_hits.get(key) or [])
			found[key] = list(dict.fromkeys(c for _n, _i, c in ranked))[:2]
	for word, script in todo:
		spellings = found.get((word, script), [])
		# none found: asked again tomorrow, when new books may hold it
		frappe.cache.set_value(
			f"resdesk:spelling:{client.books}:{script}:{word}",
			spellings,
			expires_in_sec=SPELLING_TTL if spellings else 86400,
		)
	return found


def _rewrite(tokens: list[str], spell: dict[str, list[str]], which: int) -> str | None:
	"""The query with each romanised word replaced by its `which`-th spelling (words without one
	are left out; None when no word has one)."""
	from sok_resdesk.core.translit import is_latin_word

	out, changed = [], False
	for tok in tokens:
		neg = tok.startswith("-")
		core = tok[1:] if neg else tok
		if core.startswith('"') and core.endswith('"') and len(core) >= 2:
			words = []
			for w in core[1:-1].split():
				options = spell.get(w.lower()) or []
				if options:
					words.append(options[min(which, len(options) - 1)])
					changed = True
				elif not is_latin_word(w):
					words.append(w)
			if words:
				out.append(("-" if neg else "") + '"' + " ".join(words) + '"')
			continue
		options = spell.get(core.lower()) or []
		if options:
			out.append(("-" if neg else "") + options[min(which, len(options) - 1)])
			changed = True
		elif not is_latin_word(core):
			out.append(tok)  # Indic words, numbers…: kept as they are
	return " ".join(out) if changed and out else None


def expand_query(
	q: str, filters: dict | None = None, client: MeiliClient | None = None
) -> tuple[list[str], list[dict]]:
	"""The queries to run for `q` (its OR parts, and their Indic spellings) and, for the portal,
	what else was searched: [{script, q}]."""
	from sok_resdesk.core.translit import has_indic, is_latin_word, script_of_language

	q = (q or "").strip()
	groups = [g.strip() for g in OR_SPLIT.split(q) if g.strip()] or [q]
	queries, also = list(groups), []
	latin = {
		w.lower()
		for g in groups
		for tok in TOKEN.findall(g)
		for w in tok.lstrip("-").strip('"').split()
		if is_latin_word(w)
	}
	if not latin or has_indic(q) or not romanised_on():
		return queries, also
	latin = set(sorted(latin)[: MAX_WORDS * 2])
	client = client or MeiliClient.from_settings()
	wanted = [script_of_language(lab) for lab in (filters or {}).get("language_label") or []]
	scripts = [s for s in wanted if s] or catalogue_scripts(client)[:MAX_SCRIPTS]
	if not scripts:
		return queries, also
	found = _probe(client, [(w, s) for w in latin for s in scripts])
	for script in scripts:
		spell = {w: found.get((w, script)) or [] for w in latin}
		for g in groups:
			tokens = TOKEN.findall(g)
			for which in (0, 1):
				rewritten = _rewrite(tokens, spell, which)
				if rewritten and rewritten not in queries:
					queries.append(rewritten)
					also.append({"script": script.title(), "q": rewritten})
	return queries, also


def federated(
	client: MeiliClient,
	index: str,
	queries: list[str],
	body: dict,
	page: int,
	per_page: int,
	facets: list[str] | None = None,
) -> dict:
	"""Several queries as one search: one list, best first, each document once. Returns the shape
	a plain search returns (hits, totalHits, totalPages, page, facetDistribution)."""
	per_query = {
		k: v for k, v in body.items() if k not in ("q", "page", "hitsPerPage", "facets", "limit", "offset")
	}
	federation: dict = {"offset": (page - 1) * per_page, "limit": per_page}
	if facets:
		federation["facetsByIndex"] = {index: facets}
		federation["mergeFacets"] = {}
	result = client._req(
		"POST",
		"/multi-search",
		json={
			"federation": federation,
			"queries": [{"indexUid": index, "q": q, **per_query} for q in queries],
		},
	)
	total = result.get("estimatedTotalHits", 0)
	return {
		"hits": result.get("hits", []),
		"totalHits": total,
		"totalPages": -(-total // per_page) if per_page else 0,
		"page": page,
		"facetDistribution": result.get("facetDistribution", {}),
		"processingTimeMs": result.get("processingTimeMs"),
	}
