"""Minimal, polite Internet Archive client.

Uses only public, unauthenticated endpoints:

* Advanced search - counting matches (rows=0)
* Scrape API  - cursor-based listing, no 10k result cap
  https://archive.org/services/search/v1/scrape
* Metadata API - full record + file list
  https://archive.org/metadata/{identifier}
* Page-level OCR text produced by IA's hOCR pipeline:
  {id}_hocr_searchtext.txt.gz + {id}_hocr_pageindex.json.gz
  (pageindex holds [text_start, text_end, hocr_start, hocr_end] per leaf)
"""

from __future__ import annotations

import gzip
import json
import time
from collections.abc import Iterator

import requests

SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
ADVANCED_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

SCRAPE_FIELDS = "identifier,title,addeddate"


class IAError(Exception):
	pass


class IAClient:
	def __init__(self, contact: str = "", delay: float = 0.5, timeout: int = 60, session=None):
		self.delay = delay
		self.timeout = timeout
		self.session = session or requests.Session()
		agent = "SoK-ResearchDesk/0.11 (+https://github.com/ServantsOfKnowledge/researchdesk)"
		if contact:
			agent += f" contact:{contact}"
		self.session.headers["User-Agent"] = agent
		self._last = 0.0

	# -- plumbing -------------------------------------------------------------
	def _get(self, url: str, **kwargs) -> requests.Response:
		wait = self.delay - (time.monotonic() - self._last)
		if wait > 0:
			time.sleep(wait)
		for attempt in range(4):
			try:
				resp = self.session.get(url, timeout=self.timeout, **kwargs)
				self._last = time.monotonic()
				if resp.status_code in (429, 502, 503, 504):
					time.sleep(2**attempt * 2)
					continue
				return resp
			except requests.RequestException as exc:
				if attempt == 3:
					raise IAError(f"{url}: {exc}") from exc
				time.sleep(2**attempt)
		raise IAError(f"{url}: gave up after retries")

	# -- queries --------------------------------------------------------------
	@staticmethod
	def build_query(
		scope_type: str,
		collection: str = "",
		extra_filter: str = "",
		query: str = "",
		identifiers: list[str] | None = None,
	) -> str:
		"""Turn an ingest profile into an IA Lucene query."""
		if scope_type == "Identifier List":
			ids = [i.strip() for i in (identifiers or []) if i.strip()]
			if not ids:
				raise IAError("Identifier list is empty")
			return "identifier:(" + " OR ".join(ids) + ")"
		if scope_type == "Search Query":
			if not query.strip():
				raise IAError("Search query is empty")
			base = f"({query.strip()})"
		else:
			if not collection.strip():
				raise IAError("Collection is empty")
			base = f"collection:({collection.strip()})"
		if extra_filter.strip():
			base += f" AND ({extra_filter.strip()})"
		# Research Desk is about texts; skip audio/video/collection records.
		return base + " AND mediatype:(texts)"

	def count(self, query: str) -> int:
		# advancedsearch with rows=0 is the reliable way to count; the scrape API's
		# total_only flag has been seen returning stale totals.
		resp = self._get(ADVANCED_URL, params={"q": query, "rows": 0, "output": "json"})
		if resp.status_code != 200:
			raise IAError(f"IA search failed ({resp.status_code}): {resp.text[:200]}")
		return int(resp.json().get("response", {}).get("numFound", 0))

	def iter_identifiers(self, query: str, limit: int = 0, page_size: int = 1000) -> Iterator[str]:
		"""Yield identifiers matching `query`, following the scrape cursor."""
		cursor = None
		seen = 0
		page_size = max(100, min(page_size, 10000))
		while True:
			params = {"q": query, "fields": SCRAPE_FIELDS, "count": page_size, "sorts": "addeddate desc"}
			if cursor:
				params["cursor"] = cursor
			resp = self._get(SCRAPE_URL, params=params)
			if resp.status_code != 200:
				raise IAError(f"IA search failed ({resp.status_code}): {resp.text[:200]}")
			data = resp.json()
			for item in data.get("items", []):
				yield item["identifier"]
				seen += 1
				if limit and seen >= limit:
					return
			cursor = data.get("cursor")
			if not cursor:
				return

	def metadata(self, identifier: str) -> dict:
		resp = self._get(METADATA_URL.format(identifier=identifier))
		if resp.status_code != 200:
			raise IAError(f"metadata {identifier}: HTTP {resp.status_code}")
		data = resp.json()
		if not data or "metadata" not in data:
			raise IAError(f"metadata {identifier}: item not found or dark")
		return data

	def _download(self, identifier: str, filename: str) -> bytes | None:
		resp = self._get(DOWNLOAD_URL.format(identifier=identifier, filename=filename))
		if resp.status_code != 200:
			return None
		return resp.content

	def page_texts(self, identifier: str, page_numbers: dict | None = None) -> list[dict]:
		"""Return [{leaf, label, text}] for every page with OCR text.

		`leaf` is the 0-based page index BookReader uses (…/page/n{leaf}).
		`label` is the printed page number when IA detected one.
		"""
		raw_text = self._download(identifier, f"{identifier}_hocr_searchtext.txt.gz")
		raw_index = self._download(identifier, f"{identifier}_hocr_pageindex.json.gz")
		if not raw_text or not raw_index:
			return []
		text = gzip.decompress(raw_text).decode("utf-8", errors="replace")
		index = json.loads(gzip.decompress(raw_index))
		labels = {}
		for n, page in enumerate((page_numbers or {}).get("pages", []) or []):
			labels[n] = str(page.get("pageNumber") or "")
		pages = []
		for leaf, entry in enumerate(index):
			start, end = entry[0], entry[1]
			page_text = text[start:end].strip()
			if page_text:
				pages.append({"leaf": leaf, "label": labels.get(leaf, ""), "text": page_text})
		return pages

	def djvu_text(self, identifier: str, files: list[dict]) -> str:
		"""Fallback: whole-book plain text when page-level text is unavailable."""
		for f in files:
			name = f.get("name", "")
			if name.endswith("_djvu.txt"):
				data = self._download(identifier, name)
				return data.decode("utf-8", errors="replace") if data else ""
		return ""
