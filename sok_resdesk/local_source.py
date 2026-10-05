"""Ingest IA-style item folders from a local/NAS folder or a web server.

Security: folder sources are limited to *library roots*. By default that is
``/library-source`` (the LIBRARY_DIR mounted by Docker); add more with the
site config key ``resdesk_library_roots`` (a list of absolute paths). Only an
item's PDF and cover image are ever served to readers.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import frappe
import requests

from sok_resdesk.catalogue import item_to_record, upsert_item
from sok_resdesk.core import calibre, leafimages
from sok_resdesk.core.deposit import DepositStore
from sok_resdesk.core.folder import FolderStore, HttpStore, ItemStore, StoreError, open_store
from sok_resdesk.core.normalize import normalize_ia_item

DEFAULT_ROOT = "/library-source"
SECTION_CHARS = 3000


def library_dir() -> str:
	"""Where /library-source really is: the Docker mount, or LIBRARY_DIR on a native install."""
	return frappe.conf.get("resdesk_library_dir") or DEFAULT_ROOT


def deposits_root() -> str:
	"""Where deposited works live: writable, unlike the library folder (docs/deposit.md)."""
	return frappe.get_site_path("private", "deposits")


def library_roots() -> list[str]:
	roots = frappe.conf.get("resdesk_library_roots") or []
	if isinstance(roots, str):
		roots = [roots]
	return [os.path.realpath(r) for r in [library_dir(), deposits_root(), *roots]]


def resolve_location(path: str) -> str:
	"""Profiles always say /library-source/...; map it to the real folder on native installs."""
	path = path.strip()
	real_dir = library_dir()
	if real_dir != DEFAULT_ROOT and (path == DEFAULT_ROOT or path.startswith(DEFAULT_ROOT + "/")):
		return real_dir.rstrip("/") + path[len(DEFAULT_ROOT) :]
	return path


def check_folder_allowed(path: str) -> str:
	real = os.path.realpath(resolve_location(path))
	for root in library_roots():
		if real == root or real.startswith(root + os.sep):
			return real
	frappe.throw(
		frappe._(
			"Folder {0} is outside the library folders ({1}). Set LIBRARY_DIR in .env, or add it to "
			"the site config key resdesk_library_roots."
		).format(path, ", ".join(library_roots()))
	)


def open_profile_store(profile) -> ItemStore:
	location = (profile.location or "").strip()
	if location.startswith(("http://", "https://")):
		return open_store("http", location, (profile.manifest_url or "").strip())
	return folder_store(check_folder_allowed(location))


def folder_store(path: str) -> ItemStore:
	"""A folder as a store: a Calibre library (it has a metadata.db) or IA-style item folders."""
	if os.path.realpath(path) == os.path.realpath(deposits_root()):
		return DepositStore(path)
	return calibre.CalibreStore(path) if calibre.is_library(path) else FolderStore(path)


def store_for_item(doc) -> ItemStore | None:
	if doc.source != "Local" or not doc.local_store:
		return None
	try:
		if doc.local_store.startswith(("http://", "https://")):
			return HttpStore(doc.local_store)
		return folder_store(check_folder_allowed(doc.local_store))
	except (StoreError, frappe.ValidationError):
		return None


def store_root(store: ItemStore) -> str:
	return store.base if isinstance(store, HttpStore) else store.root


def portable_path(path: str) -> str:
	"""Write folders under the library folder as /library-source/…, the same on Docker and native
	installs and on any server, so a catalogue can move (docs/moving.md)."""
	if not path or path.startswith(("http://", "https://")):
		return path
	real, lib = os.path.realpath(path), os.path.realpath(library_dir())
	if real == lib or real.startswith(lib + os.sep):
		return DEFAULT_ROOT + real[len(lib) :]
	return path


def relink(old_root: str, new_root: str = DEFAULT_ROOT) -> dict:
	"""Books and profiles that point into old_root now point into new_root (after a move)."""
	old_root, new_root = old_root.rstrip("/"), new_root.rstrip("/")
	like = old_root.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
	counts = {}
	values = {"old": old_root, "new": new_root, "like": like}
	for doctype, field in (("RD Item", "local_store"), ("RD Ingest Profile", "location")):
		where = f"`{field}` = %(old)s or `{field}` like %(like)s"
		counts[doctype] = frappe.db.sql(f"select count(*) from `tab{doctype}` where {where}", values)[0][0]
		frappe.db.sql(
			f"update `tab{doctype}` set `{field}` = concat(%(new)s, substring(`{field}`, char_length(%(old)s) + 1)) "
			f"where {where}",
			values,
		)
	frappe.db.commit()
	return counts


_ia_session = requests.Session()


def on_archive_org(item_id: str) -> bool:
	"""True when archive.org has a public item with this identifier."""
	try:
		resp = _ia_session.get(f"https://archive.org/metadata/{item_id}/metadata/identifier", timeout=20)
		return resp.status_code == 200 and resp.json().get("result") == item_id
	except (requests.RequestException, ValueError):
		return False


def sections_from_text(text: str) -> list[dict]:
	"""Whole-book text without page breaks → searchable sections (no reader jump)."""
	text = text.strip()
	out, start, n = [], 0, 0
	while start < len(text):
		end = min(len(text), start + SECTION_CHARS)
		if end < len(text):
			cut = text.rfind("\n", start + SECTION_CHARS // 2, end)
			end = cut if cut > 0 else end
		chunk = text[start:end].strip()
		if chunk:
			out.append({"leaf": -(n + 1), "label": f"§{n + 1}", "text": chunk})
			n += 1
		start = end
	return out


def file_url(item_id: str, name: str) -> str:
	return f"/api/method/sok_resdesk.api.file?item_id={quote(item_id, safe='')}&name={quote(name, safe='')}"


SCAN = "PDF without text (scan)"  # the same as pdfs.SCAN: a book waiting for OCR


def pdf_text(store: ItemStore, item_id: str, loc: str, pdf: str) -> tuple[list[dict], str, int]:
	"""(pages, where from, pages in the PDF) for a book whose folder has a PDF and no other text:
	the PDF's text layer, the text read with OCR here before, or nothing yet (a scan: OCR
	follows)."""
	from sok_resdesk.core.pdftext import has_text_layer, pages_from_pdf
	from sok_resdesk.pdfs import read_ocr_pages

	path = store.file_path(loc, pdf) if hasattr(store, "file_path") else None
	try:
		pages = pages_from_pdf(path or store.read(loc, pdf) or b"")
	except Exception:  # damaged, or not a PDF after all
		return [], "", 0
	if has_text_layer(pages):
		return pages, "PDF text layer", len(pages)
	ocrd = read_ocr_pages(item_id)
	if ocrd is not None:
		return ocrd, "OCR here", len(pages)
	return [], SCAN, len(pages)


def ingest_local_one(
	store: ItemStore,
	item_id: str,
	loc: str,
	profile,
	fetch_text: bool,
	force: bool = False,
	buffer=None,
) -> tuple[str, int]:
	"""Returns (outcome, pages_indexed); outcome is 'created', 'updated' or 'unchanged'."""
	from sok_resdesk.ingest import cache_enabled, write_cached_pages
	from sok_resdesk.search import SearchError, index_record

	signature = store.signature(loc, item_id)
	existing = frappe.db.get_value("RD Item", item_id, ["source_signature", "source"], as_dict=True)
	if existing and not force and existing.source_signature == signature:
		return "unchanged", 0

	data = store.load_item(item_id, loc)
	meta, files = data["metadata"], data["files"]
	record = normalize_ia_item(item_id, meta, files)

	pages, text_source = ([], "")
	if fetch_text:
		pages, text_source = store.page_texts(item_id, loc, data.get("page_numbers"))
		if not pages:
			book = store.book_text(item_id, loc)
			if book.strip():
				pages, text_source = sections_from_text(book), "djvu.txt"

	from sok_resdesk.core.folder import is_bare

	# a loose PDF's name says nothing about archive.org: never looked up there
	calibre_book = store.kind == "calibre"  # its books are its own, never looked for on archive.org
	on_ia = (
		bool(profile.check_archive_org) and not is_bare(loc) and not calibre_book and on_archive_org(item_id)
	)
	pdf, thumb = store.pdf_name(item_id, loc), store.thumb_name(loc)
	bundle = hasattr(store, "is_bundle") and store.is_bundle(loc)
	options = leafimages.sidecar_options(store.read(loc, leafimages.SIDECAR)) if bundle else {}
	restricted = record["access_status"] == "Restricted"
	if fetch_text and not pages and pdf and not on_ia:
		pages, text_source, count = pdf_text(store, item_id, loc, pdf)
		record["page_count"] = count or record.get("page_count") or 0
	if bundle:
		names = store.leaves(loc)
		record["page_count"] = len(names)
		record["item_type"] = options["item_type"]
	record.update(
		{
			"source": "Local",
			"has_page_text": bool(pages) and not restricted,
			"has_fulltext": bool(pages) and not restricted,
			"on_archive_org": on_ia,
			"local_store": portable_path(store_root(store)),
			"local_path": loc,
			"local_pdf": pdf or "",
			"local_thumb": thumb or "",
			"local_files": "\n".join(store.downloads(loc)) if hasattr(store, "downloads") else "",
			"local_images": "\n".join(store.leaves(loc)) if bundle else "",
			"text_source": text_source,
			"source_signature": signature,
		}
	)
	if not on_ia:
		record["source_url"] = ""
		record["thumbnail_url"] = file_url(item_id, thumb) if thumb else ""
		if bundle:  # the first leaf, small
			record["thumbnail_url"] = (
				f"/api/method/sok_resdesk.api.page_image?item_id={quote(item_id, safe='')}&leaf=0&width=300"
			)
		record["ark"] = record.get("ark") or ""

	name, created = upsert_item(record, raw=meta, profile=profile.name)
	if bundle:
		# the manuscript's own fields from bundle.json: set while they are empty, never over a person's edit
		current = frappe.db.get_value("RD Item", name, list(options["manuscript"]) or ["name"], as_dict=True)
		fill = {k: v for k, v in options["manuscript"].items() if not (current or {}).get(k)}
		if fill:
			frappe.db.set_value("RD Item", name, fill, update_modified=False)
	if pages and cache_enabled():
		write_cached_pages(item_id, pages)
	if pages:
		from sok_resdesk.ingest import PAGE_ORDER

		frappe.db.set_value("RD Item", name, "page_order", PAGE_ORDER, update_modified=False)
	if bundle and options["ocr"] and fetch_text and not restricted:
		text_source = SCAN  # printed leaves are read with OCR (a manuscript is transcribed by people)
		frappe.db.set_value("RD Item", name, "text_source", SCAN, update_modified=False)
	if text_source == SCAN and not restricted:
		from sok_resdesk.pdfs import forget_pages, queue_ocr

		forget_pages(item_id)
		queue_ocr(item_id)  # Settings → Catalogue → Read Scans with OCR
	try:
		record = item_to_record(frappe.get_doc("RD Item", name))
		from sok_resdesk.pagetext import apply

		# the folder's text with proofreaders' corrections laid over it (the cache keeps the folder's)
		pages = apply(item_id, pages) if not restricted else []
		if buffer is not None:
			return ("created" if created else "updated"), buffer.add(
				record, pages, replace_pages=not created, if_changed=True
			)
		count = index_record(record, pages, replace_pages=not created)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return ("created" if created else "updated"), count
