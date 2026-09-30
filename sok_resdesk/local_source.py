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
from sok_resdesk.core.folder import FolderStore, HttpStore, ItemStore, StoreError, open_store
from sok_resdesk.core.normalize import normalize_ia_item

DEFAULT_ROOT = "/library-source"
SECTION_CHARS = 3000


def library_dir() -> str:
	"""Where /library-source really is: the Docker mount, or LIBRARY_DIR on a native install."""
	return frappe.conf.get("resdesk_library_dir") or DEFAULT_ROOT


def library_roots() -> list[str]:
	roots = frappe.conf.get("resdesk_library_roots") or []
	if isinstance(roots, str):
		roots = [roots]
	return [os.path.realpath(r) for r in [library_dir(), *roots]]


def resolve_location(path: str) -> str:
	"""Profiles always say /library-source/...; map it to the real folder on native installs."""
	path = path.strip()
	real_dir = library_dir()
	if real_dir != DEFAULT_ROOT and (path == DEFAULT_ROOT or path.startswith(DEFAULT_ROOT + "/")):
		return real_dir.rstrip("/") + path[len(DEFAULT_ROOT):]
	return path


def check_folder_allowed(path: str) -> str:
	real = os.path.realpath(resolve_location(path))
	for root in library_roots():
		if real == root or real.startswith(root + os.sep):
			return real
	frappe.throw(
		frappe._("Folder {0} is outside the library folders ({1}). Set LIBRARY_DIR in .env, or add it to "
				 "the site config key resdesk_library_roots.").format(path, ", ".join(library_roots()))
	)


def open_profile_store(profile) -> ItemStore:
	location = (profile.location or "").strip()
	if location.startswith(("http://", "https://")):
		return open_store("http", location, (profile.manifest_url or "").strip())
	return FolderStore(check_folder_allowed(location))


def store_for_item(doc) -> ItemStore | None:
	if doc.source != "Local" or not doc.local_store:
		return None
	try:
		if doc.local_store.startswith(("http://", "https://")):
			return HttpStore(doc.local_store)
		return FolderStore(check_folder_allowed(doc.local_store))
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
		return DEFAULT_ROOT + real[len(lib):]
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
			f"where {where}", values)
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


def ingest_local_one(store: ItemStore, item_id: str, loc: str, profile, fetch_text: bool,
					 force: bool = False) -> tuple[str, int]:
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

	on_ia = bool(profile.check_archive_org) and on_archive_org(item_id)
	pdf, thumb = store.pdf_name(item_id, loc), store.thumb_name(loc)
	restricted = record["access_status"] == "Restricted"
	record.update({
		"source": "Local",
		"has_page_text": bool(pages) and not restricted,
		"has_fulltext": bool(pages) and not restricted,
		"on_archive_org": on_ia,
		"local_store": portable_path(store_root(store)),
		"local_path": loc,
		"local_pdf": pdf or "",
		"local_thumb": thumb or "",
		"text_source": text_source,
		"source_signature": signature,
	})
	if not on_ia:
		record["source_url"] = ""
		record["thumbnail_url"] = file_url(item_id, thumb) if thumb else ""
		record["ark"] = record.get("ark") or ""

	name, created = upsert_item(record, raw=meta, profile=profile.name)
	if pages and cache_enabled():
		write_cached_pages(item_id, pages)
	try:
		count = index_record(item_to_record(frappe.get_doc("RD Item", name)), pages if not restricted else [],
							 replace_pages=not created)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return ("created" if created else "updated"), count
