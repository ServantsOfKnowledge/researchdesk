"""Export → *Calibre library (zip)*: books the library holds files of, as a folder Calibre can add.

Which books and how they are chosen is the Export screen's (a collection, a search, selected
books…). Only files held here go in: a Local folder's or Calibre library's own files, and a
book's copy in our preservation store. Everything else is catalogued in ``not-included.csv`` with
its link, and a book that is not open to read is never written out. See core/calibre_export.py.
"""

from __future__ import annotations

import os
import shutil

import frappe
from frappe import _

from sok_resdesk.catalogue import base_url, item_to_record
from sok_resdesk.core import calibre_export as ce
from sok_resdesk.core.folder import HttpStore

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
MAX_BOOKS = 20000
SPARE = 1 << 30  # keep a gigabyte free on the disk


def folder() -> str:
	return frappe.get_site_path("private", "files")


def _store(doc, stores: dict):
	"""The folder store a local book lives in (opened once per folder), or None."""
	from sok_resdesk.local_source import check_folder_allowed, folder_store

	root = doc.local_store
	if root not in stores:
		try:
			stores[root] = (
				None if root.startswith(("http://", "https://")) else folder_store(check_folder_allowed(root))
			)
		except Exception:
			stores[root] = None
	return stores[root]


def _files(doc, stores: dict) -> tuple[list[tuple[str, str]], str]:
	"""([(file name, path)], cover path) of what is held here for the book."""
	files: list[tuple[str, str]] = []
	cover = ""
	if doc.source == "Local" and doc.local_store:
		store = _store(doc, stores)
		if store is not None and not isinstance(store, HttpStore):
			names = list(dict.fromkeys([doc.local_pdf, *(doc.local_files or "").splitlines()]))
			for name in names:
				path = name and store.file_path(doc.local_path, name)
				if path:
					files.append((name, path))
			if doc.local_thumb:
				cover = store.file_path(doc.local_path, doc.local_thumb) or ""
	if not files:
		from sok_resdesk.preservation import copy_pdf

		try:
			found = copy_pdf(doc.item_id)
		except Exception:
			found = None
		if found:
			files.append(found)
	return files, cover


def _why_not(doc) -> str:
	if doc.access_status != "Open":
		return _("Not open to read, so it is not written out")
	if doc.source == "Internet Archive" or doc.on_archive_org:
		return _("On archive.org; this library holds no copy")
	if doc.source in ("Repository", "Wikisource"):
		return _("Held by the {0}, not here").format(
			_("repository") if doc.source == "Repository" else "Wikisource"
		)
	return _("This library holds no file for it")


def gather(names: list[str], progress=None) -> tuple[list[dict], list[dict]]:
	"""(books with files held here, books without) for the chosen books."""
	books, left, stores = [], [], {}
	root = base_url()
	for n, name in enumerate(names):
		doc = frappe.get_doc("RD Item", name)
		record = item_to_record(doc)
		link = doc.source_url or (f"https://archive.org/details/{doc.item_id}" if doc.on_archive_org else "")
		files, cover = _files(doc, stores) if doc.access_status == "Open" else ([], "")
		if not files:
			left.append(
				{
					"item_id": doc.item_id,
					"title": doc.title,
					"authors": record["creators"],
					"year": doc.year,
					"why": _why_not(doc),
					"link": link or f"{root}/library/item/{doc.item_id}",
				}
			)
			continue
		portal = f"{root}/library/item/{doc.item_id}"
		books.append(
			{
				"item_id": doc.item_id,
				"uuid": ce.book_uuid(doc.item_id),
				"title": doc.title or doc.item_id,
				"authors": record["creators"],
				"date": f"{doc.year}-01-01" if doc.year else "",
				"publisher": doc.publisher or "",
				"language": doc.language or "",
				"tags": record["subjects"],
				"series": doc.series or "",
				"description": f"{doc.description or ''}\n\n{portal}".strip(),
				"identifiers": {k: v for k, v in (("isbn", doc.isbn), ("research-desk", doc.item_id)) if v},
				"files": files,
				"cover": cover,
			}
		)
		if progress and n % 200 == 0:
			progress(n)
	return books, left


def free_problem(size: int) -> str:
	"""'' when the zip fits on the disk with room to spare, else what to do."""
	os.makedirs(folder(), exist_ok=True)
	free = shutil.disk_usage(folder()).free
	if size + SPARE > free:
		return _("The books are about {0} MB and the disk has {1} MB free: choose fewer books.").format(
			size >> 20, free >> 20
		)
	return ""


def build(export_name: str, names: list[str]) -> tuple[str, int, str]:
	"""Make the zip for an Export; returns (file_url, books written, summary)."""
	if len(names) > MAX_BOOKS:
		frappe.throw(
			_("A Calibre library of {0} books is too many at once: choose up to {1}.").format(
				len(names), MAX_BOOKS
			)
		)
	books, left = gather(names)
	problem = free_problem(ce.total_size(books))
	if problem:
		frappe.throw(problem)
	fname = f"calibre-library-{export_name.lower()}.zip"
	dest = os.path.join(folder(), fname)
	count = ce.write_zip(dest, books, left)
	frappe.get_doc(
		{
			"doctype": "File",
			"file_name": fname,
			"file_url": f"/private/files/{fname}",
			"attached_to_doctype": "RD Export",
			"attached_to_name": export_name,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)
	return (
		f"/private/files/{fname}",
		len(books),
		f"{len(books)} books with {count} files ({os.path.getsize(dest) >> 20} MB); {len(left)} listed in not-included.csv",
	)


@frappe.whitelist()
def estimate(values) -> dict:
	"""How much a Calibre export of these books would hold (before making it)."""
	from sok_resdesk.transfer import select_for_export

	frappe.only_for(STAFF)
	values = frappe.parse_json(values) if isinstance(values, str) else values
	doc = frappe.get_doc({"doctype": "RD Export", **values})
	names = select_for_export(doc)
	books, left = gather(names[:MAX_BOOKS])
	size = ce.total_size(books)
	return {
		"books": len(names),
		"with_files": len(books),
		"files": sum(len(b["files"]) for b in books),
		"megabytes": size >> 20,
		"not_included": len(left),
		"problem": free_problem(size),
	}
