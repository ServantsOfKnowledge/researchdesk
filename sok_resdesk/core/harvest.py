"""Harvesting books from OAI-PMH repositories (DSpace, EPrints, Islandora, Koha, OJS…).

Most institutional and digital-library repositories publish their catalogue over OAI-PMH 2.0,
in simple Dublin Core (oai_dc) at least. Research Desk harvests the records, catalogues them
with the same clean-up as archive.org's (languages, dates, authors, subjects), and finds each
record's PDF: in the record itself, or from the record's landing page, which DSpace, EPrints
and OJS all mark for Google Scholar (``<meta name="citation_pdf_url">``). The PDF's text, page
by page, becomes the book's page text. The repository stays the store of record: readers get
its landing page and PDF.

Records are listed with ``ListRecords`` (resumption tokens followed), only those changed since
the last harvest on later runs (``from``), and records the repository marks deleted are taken
off the portal.

Pure Python (requests and the standard library) so it is unit-tested directly.

Spec: https://www.openarchives.org/OAI/openarchivesprotocol.html
"""

from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

OAI = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
OAI_DC = "{http://www.openarchives.org/OAI/2.0/oai_dc/}"
USER_AGENT = "SOK-ResearchDesk/1.0 (+https://github.com/ServantsOfKnowledge/researchdesk)"
DC_FIELDS = (
	"title",
	"creator",
	"contributor",
	"subject",
	"description",
	"publisher",
	"date",
	"type",
	"format",
	"identifier",
	"source",
	"language",
	"relation",
	"coverage",
	"rights",
)
MAX_PDF_BYTES = 300 * 1024 * 1024  # a PDF bigger than this is linked, not read


class HarvestError(Exception):
	pass


# -- the protocol --------------------------------------------------------------------------------


class Harvester:
	"""An OAI-PMH client: Identify, ListSets, ListRecords (all pages), GetRecord."""

	def __init__(self, base_url: str, session=None, delay: float = 1.0, sleep=time.sleep, timeout: int = 90):
		base_url = (base_url or "").strip()
		if not re.match(r"^https?://", base_url):
			raise HarvestError("The repository's OAI-PMH address must start with http:// or https://")
		self.base_url = base_url.split("?")[0]
		self.session = session or requests.Session()
		self.session.headers.setdefault("User-Agent", USER_AGENT)
		self.delay, self.sleep, self.timeout = delay, sleep, timeout
		self._last = 0.0

	def _get(self, params: dict) -> ET.Element | None:
		"""One request. None when the repository has nothing to list (noRecordsMatch)."""
		for attempt in range(5):
			wait = self.delay - (time.monotonic() - self._last)
			if wait > 0:
				self.sleep(wait)
			self._last = time.monotonic()
			try:
				resp = self.session.get(self.base_url, params=params, timeout=self.timeout)
			except requests.RequestException as e:
				if attempt == 4:
					raise HarvestError(f"Cannot reach {self.base_url}: {e}") from e
				self.sleep(5 * (attempt + 1))
				continue
			if resp.status_code in (429, 503) and attempt < 4:
				# the protocol's own way of saying "not now"
				retry = resp.headers.get("Retry-After", "")
				self.sleep(min(int(retry) if retry.isdigit() else 10 * (attempt + 1), 300))
				continue
			if resp.status_code >= 400:
				raise HarvestError(f"{self.base_url} answered {resp.status_code}")
			try:
				root = ET.fromstring(resp.content)
			except ET.ParseError as e:
				raise HarvestError(f"{self.base_url} did not answer in OAI-PMH XML: {e}") from e
			err = root.find(f"{OAI}error")
			if err is not None:
				code = err.get("code", "")
				if code in ("noRecordsMatch", "noSetHierarchy"):
					return None
				raise HarvestError(f"{code}: {(err.text or '').strip()}")
			return root
		raise HarvestError(f"{self.base_url} kept asking to wait")

	def identify(self) -> dict:
		root = self._get({"verb": "Identify"})
		node = root.find(f"{OAI}Identify") if root is not None else None
		if node is None:
			raise HarvestError("No Identify answer: is this an OAI-PMH address?")

		def text(tag):
			return (node.findtext(f"{OAI}{tag}") or "").strip()

		return {
			"name": text("repositoryName"),
			"base_url": text("baseURL"),
			"granularity": text("granularity") or "YYYY-MM-DD",
			"earliest": text("earliestDatestamp"),
			"admin_email": text("adminEmail"),
			"deleted": text("deletedRecord"),
		}

	def list_sets(self) -> list[tuple[str, str]]:
		out, params = [], {"verb": "ListSets"}
		while True:
			root = self._get(params)
			node = root.find(f"{OAI}ListSets") if root is not None else None
			if node is None:
				return out
			for s in node.findall(f"{OAI}set"):
				out.append(
					((s.findtext(f"{OAI}setSpec") or "").strip(), (s.findtext(f"{OAI}setName") or "").strip())
				)
			token = (node.findtext(f"{OAI}resumptionToken") or "").strip()
			if not token:
				return out
			params = {"verb": "ListSets", "resumptionToken": token}

	def records(
		self, prefix: str = "oai_dc", set_spec: str = "", from_: str = "", until: str = ""
	) -> Iterator[dict]:
		"""Every record (deleted ones too, marked), following resumption tokens."""
		params = {"verb": "ListRecords", "metadataPrefix": prefix or "oai_dc"}
		if set_spec:
			params["set"] = set_spec
		if from_:
			params["from"] = from_
		if until:
			params["until"] = until
		while True:
			root = self._get(params)
			node = root.find(f"{OAI}ListRecords") if root is not None else None
			if node is None:
				return
			for rec in node.findall(f"{OAI}record"):
				yield parse_record(rec)
			token = (node.findtext(f"{OAI}resumptionToken") or "").strip()
			if not token:
				return
			params = {"verb": "ListRecords", "resumptionToken": token}

	def count(self, prefix: str = "oai_dc", set_spec: str = "") -> int | None:
		"""How many records there are, from the first page of identifiers: the repository's
		completeListSize when it gives one (DSpace and EPrints do), else None when there is more
		than one page."""
		params = {"verb": "ListIdentifiers", "metadataPrefix": prefix or "oai_dc"}
		if set_spec:
			params["set"] = set_spec
		root = self._get(params)
		node = root.find(f"{OAI}ListIdentifiers") if root is not None else None
		if node is None:
			return 0
		token = node.find(f"{OAI}resumptionToken")
		if token is not None and (token.get("completeListSize") or "").isdigit():
			return int(token.get("completeListSize"))
		if token is None or not (token.text or "").strip():
			return len(node.findall(f"{OAI}header"))
		return None

	def raw_records(self, prefix: str = "marc21", set_spec: str = "", from_: str = "") -> Iterator[tuple]:
		"""(identifier, deleted, metadata element) for every record, in any metadata format (a
		library system's MARCXML, for core/marcin.py), following resumption tokens."""
		params = {"verb": "ListRecords", "metadataPrefix": prefix}
		if set_spec:
			params["set"] = set_spec
		if from_:
			params["from"] = from_
		while True:
			root = self._get(params)
			node = root.find(f"{OAI}ListRecords") if root is not None else None
			if node is None:
				return
			for rec in node.findall(f"{OAI}record"):
				header = rec.find(f"{OAI}header")
				meta = rec.find(f"{OAI}metadata")
				yield (
					(header.findtext(f"{OAI}identifier") or "").strip() if header is not None else "",
					header is not None and header.get("status") == "deleted",
					meta[0] if meta is not None and len(meta) else None,
				)
			token = (node.findtext(f"{OAI}resumptionToken") or "").strip()
			if not token:
				return
			params = {"verb": "ListRecords", "resumptionToken": token}

	def get_record(self, identifier: str, prefix: str = "oai_dc") -> dict | None:
		root = self._get(
			{"verb": "GetRecord", "identifier": identifier, "metadataPrefix": prefix or "oai_dc"}
		)
		rec = root.find(f"{OAI}GetRecord/{OAI}record") if root is not None else None
		return parse_record(rec) if rec is not None else None


def parse_record(rec: ET.Element) -> dict:
	"""An OAI record → {identifier, datestamp, deleted, sets, dc: {field: [values]}}."""
	header = rec.find(f"{OAI}header")
	dc: dict[str, list[str]] = {}
	meta = rec.find(f"{OAI}metadata")
	if meta is not None:
		for el in meta.iter():
			if el.tag.startswith(DC):
				field = el.tag[len(DC) :]
				value = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
				if field in DC_FIELDS and value:
					dc.setdefault(field, []).append(value)
	return {
		"identifier": (header.findtext(f"{OAI}identifier") or "").strip() if header is not None else "",
		"datestamp": (header.findtext(f"{OAI}datestamp") or "").strip() if header is not None else "",
		"deleted": header is not None and header.get("status") == "deleted",
		"sets": [(s.text or "").strip() for s in header.findall(f"{OAI}setSpec")]
		if header is not None
		else [],
		"dc": dc,
	}


# -- from a record to a catalogue entry -----------------------------------------------------------


def item_id_for(oai_identifier: str, prefix: str) -> str:
	"""A stable catalogue identifier for a record: the library's prefix for the repository and
	the record's own local part (``oai:dspace.example.org:123456789/42`` → ``uni-123456789-42``).
	Only letters, digits, dots, hyphens and underscores, as archive.org identifiers; a long one
	(or one with nothing usable) is shortened with a fingerprint so two records never meet."""
	local = oai_identifier.split(":", 2)[-1] if oai_identifier.startswith("oai:") else oai_identifier
	safe = re.sub(r"[^A-Za-z0-9._-]+", "-", local).strip("-._")
	prefix = re.sub(r"[^A-Za-z0-9._-]+", "-", prefix or "oai").strip("-._") or "oai"
	ident = f"{prefix}-{safe}" if safe else prefix
	if len(ident) > 100 or not safe:
		ident = f"{ident[:90]}-{hashlib.sha1(oai_identifier.encode()).hexdigest()[:8]}"
	return ident


def _urls(values: list[str]) -> list[str]:
	return [v for v in values if re.match(r"^https?://\S+$", v)]


def links(dc: dict) -> dict:
	"""{landing, pdf}: the record's web page and PDF, where the record says them. DOIs and
	handles come first for the landing page: they outlive a repository's own addresses."""
	urls = _urls(dc.get("identifier", []) + dc.get("relation", []) + dc.get("source", []))
	pdf = next(
		(u for u in urls if re.search(r"\.pdf($|\?)", u, re.I) or "/bitstream/" in u or "/download/" in u),
		"",
	)
	pages = [u for u in urls if u != pdf]
	landing = next(
		(u for u in pages if "doi.org/" in u or "hdl.handle.net/" in u),
		next((u for u in pages if not re.search(r"\.(jpe?g|png|gif|tiff?|xml)($|\?)", u, re.I)), ""),
	)
	# a DOI as plain text (10.1234/abc) is a landing page too
	if not landing:
		doi = next((v for v in dc.get("identifier", []) if re.match(r"^(doi:)?10\.\d{4,}/\S+$", v)), "")
		if doi:
			landing = "https://doi.org/" + doi.removeprefix("doi:")
	return {"landing": landing, "pdf": pdf}


def to_meta(record: dict, repository: str = "") -> dict:
	"""Dublin Core → the archive.org-style metadata the catalogue's clean-up reads."""
	dc = record["dc"]
	meta: dict = {
		"title": dc.get("title", [])[:1],
		"creator": dc.get("creator", []),
		"subject": dc.get("subject", []),
		"description": dc.get("description", []),
		"publisher": dc.get("publisher", [])[:1],
		"date": _best_date(dc.get("date", [])),
		"language": dc.get("language", [])[:1],
		"type": dc.get("type", []),
	}
	if len(dc.get("title", [])) > 1:
		meta["alt_title"] = dc["title"][1]
	rights = dc.get("rights", [])
	licence = next(
		(r for r in rights if re.match(r"^https?://\S*(creativecommons|license|licence)", r, re.I)), ""
	)
	if licence:
		meta["licenseurl"] = licence
	text_rights = [r for r in rights if r != licence]
	if text_rights:
		meta["rights"] = text_rights[0]
	isbn = next(
		(i for i in dc.get("identifier", []) if re.match(r"^(isbn:?\s*)?[\d-]{10,17}[\dxX]?$", i, re.I)), ""
	)
	if isbn:
		meta["isbn"] = re.sub(r"(?i)^isbn:?\s*", "", isbn)
	if repository:
		meta["collection"] = [repository]
	return {k: v for k, v in meta.items() if v}


def _best_date(dates: list[str]) -> str:
	"""Repositories list several dates (accessioned, available, issued): the issued one is the
	earliest that is a plain year or date, usually."""
	plain = [d for d in dates if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", d)]
	return min(plain) if plain else (dates[0] if dates else "")


# -- the record's PDF --------------------------------------------------------------------------


class _Meta(HTMLParser):
	def __init__(self):
		super().__init__()
		self.pdf, self.links = "", []

	def handle_starttag(self, tag, attrs):
		a = dict(attrs)
		if tag == "meta" and (a.get("name") or "").lower() == "citation_pdf_url" and a.get("content"):
			self.pdf = self.pdf or a["content"]
		elif tag == "a" and a.get("href"):
			self.links.append(a["href"])


def pdf_from_landing(html: str, page_url: str) -> str:
	"""The PDF a landing page offers: its citation_pdf_url (DSpace, EPrints, OJS and most
	repositories set it for Google Scholar), else the first link to a .pdf or a bitstream."""
	p = _Meta()
	try:
		p.feed(html)
	except Exception:
		return ""
	if p.pdf:
		return urljoin(page_url, p.pdf)
	for href in p.links:
		if re.search(r"\.pdf($|\?)", href, re.I) or "/bitstream/" in href:
			return urljoin(page_url, href)
	return ""


def same_site(url: str, other: str) -> bool:
	return urlparse(url).netloc.lower().removeprefix("www.") == urlparse(other).netloc.lower().removeprefix(
		"www."
	)
