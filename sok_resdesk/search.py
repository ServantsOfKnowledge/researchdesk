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
import re

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.catalogue import item_to_record, settings
from sok_resdesk.core.normalize import decade_of

BOOK_SETTINGS = {
	"searchableAttributes": [
		"title", "alt_title", "creators", "alt_creators", "subjects", "series", "publisher",
		"description", "item_id", "text_excerpt",
	],
	"filterableAttributes": [
		"item_id", "language", "language_label", "year", "decade", "creators", "subjects", "collections",
		"access_status", "has_fulltext", "source", "visibility", "curated", "item_type",
	],
	"sortableAttributes": ["year", "title_sort", "indexed_at"],
	"displayedAttributes": ["*"],
	"faceting": {"maxValuesPerFacet": 200, "sortFacetValuesBy": {"*": "count"}},
	"pagination": {"maxTotalHits": 10000},
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
	"filterableAttributes": ["item_id", "language_label", "year", "decade", "collections", "creators", "visibility",
							 "curated", "item_type", "subjects"],
	"sortableAttributes": ["leaf"],
	"displayedAttributes": ["*"],
	"pagination": {"maxTotalHits": 10000},
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
		docs.append({
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
		})
	return docs


# -- indexing -------------------------------------------------------------------

def index_record(record: dict, pages: list[dict] | None = None, client: MeiliClient | None = None,
				 replace_pages: bool = True) -> int:
	"""Index one book and (optionally) its pages. Returns number of pages indexed."""
	client = client or MeiliClient.from_settings()
	s = settings()
	pages = pages or []
	excerpt = " ".join(p["text"] for p in pages[:6])
	client.add(client.books, [book_document(record, excerpt)])
	count = 0
	if pages and cint(s.index_pages):
		if replace_pages:  # new books have no old pages to remove
			client.delete_by_filter(client.pages, f"item_id = {_quote(record['item_id'])}")
		docs = page_documents(record, pages, cint(s.max_page_chars) or 6000)
		for i in range(0, len(docs), 500):
			client.add(client.pages, docs[i:i + 500])
		count = len(docs)
	frappe.db.set_value(
		"RD Item", record["item_id"],
		{"indexed_on": now_datetime(), **({"indexed_pages": count} if pages else {})},
		update_modified=False,
	)
	return count


PAGE_FIELDS = ("creators", "year", "decade", "language_label", "collections", "visibility", "curated",
			   "item_type", "subjects")


def update_item_fields(names: list[str], client: MeiliClient | None = None, wait: bool = False) -> None:
	"""Push catalogue edits (metadata, visibility, collections) to both indexes without
	re-indexing page text. Book documents keep their text excerpt; page documents get the
	fields they carry for filtering. Batched: one index task per 500 books / 10,000 pages."""
	client = client or MeiliClient.from_settings()
	names = [n for n in dict.fromkeys(names) if n]
	last = None
	for i in range(0, len(names), 200):
		chunk = frappe.get_all("RD Item", filters={"name": ("in", names[i:i + 200]), "published": 1}, pluck="name")
		if not chunk:
			continue
		books = {}
		for name in chunk:
			doc = book_document(item_to_record(frappe.get_doc("RD Item", name)))
			doc.pop("indexed_at", None)
			books[name] = doc
		flt = f"item_id IN [{', '.join(_quote(n) for n in chunk)}]"
		indexed = {d["item_id"] for d in client._req("POST", f"/indexes/{client.books}/documents/fetch",
													 json={"filter": flt, "fields": ["item_id"], "limit": 1000}).get("results", [])}
		new = [dict(b, text_excerpt="") for n, b in books.items() if n not in indexed]
		if new:
			last = client.add(client.books, new)
		partial = [{k: v for k, v in b.items() if k != "text_excerpt"} for n, b in books.items() if n in indexed]
		if partial:
			last = client._req("PUT", f"/indexes/{client.books}/documents", json=partial)
		updates, offset = [], 0
		while True:
			res = client._req("POST", f"/indexes/{client.pages}/documents/fetch",
							  json={"filter": flt, "fields": ["id", "item_id"], "limit": 10000, "offset": offset})
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
		frappe.db.set_single_value("RD Settings", "search_status", f"Error: {e}")
		frappe.throw(str(e))
	books = stats.get(client.books, {}).get("numberOfDocuments", 0)
	pages = stats.get(client.pages, {}).get("numberOfDocuments", 0)
	msg = _("Connected ({0}). Indexes ready: {1} books, {2} pages.").format(health.get("status"), books, pages)
	frappe.db.set_single_value("RD Settings", "search_status", msg)
	return msg


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


def queue_rebuild(with_pages: int = 1, batch_size: int = 50) -> int:
	"""Split a full re-index into batches that the queue workers run in parallel."""
	frappe.cache.delete_value("resdesk:stop-background")  # a new rebuild overrides an earlier "stop everything"
	MeiliClient.from_settings().setup()
	names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	for n, i in enumerate(range(0, len(names), batch_size), 1):
		frappe.enqueue(
			"sok_resdesk.search.rebuild_batch", queue="long", timeout=6 * 3600,
			names=names[i:i + batch_size], with_pages=with_pages, job_id=f"resdesk-reindex-{n}",
		)
	return len(names)


def rebuild_batch(names: list[str], with_pages: int = 1, verbose: bool = False) -> int:
	from sok_resdesk.ingest import fetch_pages

	client = MeiliClient.from_settings()
	for n, name in enumerate(names, 1):
		if frappe.cache.get_value("resdesk:stop-background"):
			break  # "Stop everything" on the Background Jobs page
		frappe.db.commit()
		doc = frappe.get_doc("RD Item", name)
		pages = []
		if with_pages and doc.has_page_text:
			try:
				pages = fetch_pages(doc.item_id)  # local cache first, archive.org only if missing
			except Exception as e:  # keep going; one bad item should not stop a rebuild
				frappe.log_error("Research Desk: page fetch failed", f"{name}: {e}")
		index_record(item_to_record(doc), pages, client)
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
	books = client.search(client.books, {
		"q": "", "limit": len(ids), "filter": f"item_id IN [{', '.join(_quote(i) for i in ids)}]",
		"attributesToRetrieve": ["item_id", "title", "alt_title", "creators"],
	}).get("hits", [])
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


def search(q: str = "", mode: str = "books", filters: dict | None = None, page: int = 1,
		   per_page: int = 20, sort: str = "", access: dict | None = None) -> dict:
	"""access: {"books": filter, "pages": filter} from access.search_filter; None = no limit, "" = nothing."""
	access = access or {}
	if access.get(mode) == "":
		return {"hits": [], "totalHits": 0, "totalPages": 0, "page": 1, "facetDistribution": {}, "restricted": True}
	client = MeiliClient.from_settings()
	page, per_page = max(1, cint(page)), min(max(1, cint(per_page)), 100)
	body: dict = {"q": q or "", "page": page, "hitsPerPage": per_page, "filter": build_filter(filters)}
	if access.get(mode):
		body["filter"].append(access[mode])
	if mode == "pages":
		body.update({
			"attributesToCrop": ["text"], "cropLength": 40,
			"attributesToHighlight": ["text"], "highlightPreTag": "<mark>", "highlightPostTag": "</mark>",
			"attributesToRetrieve": ["item_id", "leaf", "label", "year", "language_label", "visibility"],
		})
		result = client.search(client.pages, body)
		_attach_book_fields(client, result.get("hits", []))
		# facet counts always come from the books index so the sidebar stays useful
		book_filter = build_filter(filters) + ([access["books"]] if access.get("books") else [])
		facets = client.search(client.books, {"q": "", "limit": 0, "facets": FACETS, "filter": book_filter})
		result["facetDistribution"] = facets.get("facetDistribution", {})
	else:
		body.update({
			"facets": FACETS,
			"attributesToCrop": ["description", "text_excerpt"], "cropLength": 30,
			"attributesToHighlight": ["title", "alt_title", "creators", "description", "text_excerpt"],
			"highlightPreTag": "<mark>", "highlightPostTag": "</mark>",
		})
		if sort in ("year:asc", "year:desc", "title_sort:asc"):
			body["sort"] = [sort]
		result = client.search(client.books, body)
	return result
