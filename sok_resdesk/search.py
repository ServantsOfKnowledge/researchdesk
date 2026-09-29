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
		"language", "language_label", "year", "decade", "creators", "subjects", "collections",
		"access_status", "has_fulltext", "source",
	],
	"sortableAttributes": ["year", "title_sort", "indexed_at"],
	"displayedAttributes": ["*"],
	"faceting": {"maxValuesPerFacet": 200, "sortFacetValuesBy": {"*": "count"}},
	"pagination": {"maxTotalHits": 10000},
}
PAGE_SETTINGS = {
	"searchableAttributes": ["text", "title", "alt_title"],
	"filterableAttributes": ["item_id", "language_label", "year", "decade", "collections", "creators"],
	"sortableAttributes": ["year", "leaf"],
	"displayedAttributes": ["*"],
	"pagination": {"maxTotalHits": 10000},
}
FACETS = ["language_label", "decade", "subjects", "creators", "collections"]


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
			"title": record.get("title"),
			"alt_title": record.get("alt_title"),
			"creators": record.get("creators") or [],
			"year": record.get("year"),
			"decade": record.get("decade") or decade_of(record.get("year")),
			"language_label": record.get("language_label") or "Unknown",
			"collections": record.get("collections") or [],
		})
	return docs


# -- indexing -------------------------------------------------------------------

def index_record(record: dict, pages: list[dict] | None = None, client: MeiliClient | None = None) -> int:
	"""Index one book and (optionally) its pages. Returns number of pages indexed."""
	client = client or MeiliClient.from_settings()
	s = settings()
	pages = pages or []
	excerpt = " ".join(p["text"] for p in pages[:6])
	client.add(client.books, [book_document(record, excerpt)])
	count = 0
	if pages and cint(s.index_pages):
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
			client.add(client.books, [book_document(item_to_record(doc))])
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
	frappe.enqueue(
		"sok_resdesk.search.rebuild_all", queue="long", timeout=6 * 3600, with_pages=cint(with_pages),
		job_id="resdesk-rebuild", deduplicate=True,
	)


def rebuild_all(with_pages: int = 1, verbose: bool = False) -> int:
	from sok_resdesk.ingest import fetch_pages

	client = MeiliClient.from_settings()
	client.setup()
	names = frappe.get_all("RD Item", filters={"published": 1}, pluck="name", order_by="creation asc")
	for n, name in enumerate(names, 1):
		doc = frappe.get_doc("RD Item", name)
		pages = []
		if with_pages and doc.has_page_text:
			try:
				pages = fetch_pages(doc.item_id)
			except Exception as e:  # keep going; one bad item should not stop a rebuild
				frappe.log_error("Research Desk: page fetch failed", f"{name}: {e}")
		index_record(item_to_record(doc), pages, client)
		if n % 20 == 0:
			frappe.db.commit()
		if verbose:
			print(f"[{n}/{len(names)}] {name} ({len(pages)} pages)")
	frappe.db.commit()
	return len(names)


# -- public search ----------------------------------------------------------------

def build_filter(filters: dict | None) -> list:
	parts: list = []
	for field, values in (filters or {}).items():
		if field in ("year_from", "year_to"):
			continue
		if field not in FACETS + ["language", "item_id", "access_status"]:
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
		   per_page: int = 20, sort: str = "") -> dict:
	client = MeiliClient.from_settings()
	page, per_page = max(1, cint(page)), min(max(1, cint(per_page)), 100)
	body: dict = {"q": q or "", "page": page, "hitsPerPage": per_page, "filter": build_filter(filters)}
	if mode == "pages":
		body.update({
			"attributesToCrop": ["text"], "cropLength": 40,
			"attributesToHighlight": ["text"], "highlightPreTag": "<mark>", "highlightPostTag": "</mark>",
			"attributesToRetrieve": ["item_id", "leaf", "label", "title", "alt_title", "creators", "year", "language_label"],
		})
		result = client.search(client.pages, body)
		# facet counts always come from the books index so the sidebar stays useful
		facets = client.search(client.books, {"q": "", "limit": 0, "facets": FACETS, "filter": body["filter"]})
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
