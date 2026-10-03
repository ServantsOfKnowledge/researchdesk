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

from sok_resdesk.core import scandata

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
		agent = "SOK-ResearchDesk/0.11 (+https://github.com/ServantsOfKnowledge/researchdesk)"
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

	def download_file(self, identifier: str, filename: str, dest: str) -> dict:
		"""Stream one file of an item to `dest` (big scans don't go through memory).
		Returns {"bytes", "md5"} so the caller can compare with the md5 archive.org lists."""
		import hashlib
		from urllib.parse import quote

		url = DOWNLOAD_URL.format(identifier=identifier, filename=quote(filename))
		resp = self._get(url, stream=True)
		if resp.status_code != 200:
			raise IAError(f"{identifier}/{filename}: HTTP {resp.status_code}")
		md5, size = hashlib.md5(), 0
		with open(dest, "wb") as f:
			for block in resp.iter_content(1 << 20):
				f.write(block)
				md5.update(block)
				size += len(block)
		return {"bytes": size, "md5": md5.hexdigest()}

	def scan_leaves(self, identifier: str, files: list[dict]) -> list:
		"""The item's scan data (core/scandata.py): which leaves the book shows."""
		name = scandata.file_name(identifier, [f.get("name", "") for f in files or []])
		if not name:
			return []
		data = self._download(identifier, name)
		return scandata.parse(scandata.from_zip(data) if name.endswith(".zip") else data)

	def page_texts(
		self, identifier: str, page_numbers: dict | None = None, files: list[dict] | None = None
	) -> list[dict]:
		"""Return [{leaf, label, text}] for every page with OCR text.

		`leaf` is the 0-based page index BookReader uses (…/page/n{leaf}): the OCR counts every
		leaf scanned, so the scan data (from `files`) says which ones the book shows.
		`label` is the printed page number when IA detected one.
		"""
		raw_text = self._download(identifier, f"{identifier}_hocr_searchtext.txt.gz")
		raw_index = self._download(identifier, f"{identifier}_hocr_pageindex.json.gz")
		if not raw_text or not raw_index:
			return []
		text = gzip.decompress(raw_text).decode("utf-8", errors="replace")
		index = json.loads(gzip.decompress(raw_index))
		leaves = self.scan_leaves(identifier, files) if files else []
		return scandata.pages([text[e[0] : e[1]] for e in index], page_numbers, leaves)

	def djvu_text(self, identifier: str, files: list[dict]) -> str:
		"""Fallback: whole-book plain text when page-level text is unavailable."""
		for f in files:
			name = f.get("name", "")
			if name.endswith("_djvu.txt"):
				data = self._download(identifier, name)
				return data.decode("utf-8", errors="replace") if data else ""
		return ""
