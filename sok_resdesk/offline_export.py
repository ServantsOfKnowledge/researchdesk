"""Export → *Offline copy (zip, for Kiwix)*: a collection as a folder of web pages that opens with
no server and no internet, and that Kiwix can package as a ZIM file (core/offline.py).

Only books that are open to read and public get their files and text in the copy: it goes
anywhere a person carries it, so a members-only or restricted book is listed by its details alone.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import frappe
from frappe import _
from frappe.utils import now_datetime

from sok_resdesk.calibre_export import MAX_BOOKS, STAFF, _files, folder, free_problem
from sok_resdesk.catalogue import base_url, item_to_record, portal_title
from sok_resdesk.core import offline

ZIM_TIMEOUT = 6 * 3600


def _book(doc, stores: dict, with_files: bool) -> dict:
	from sok_resdesk.ingest import read_cached_pages

	record = item_to_record(doc)
	public = doc.access_status == "Open" and (doc.visibility or "Public") == "Public"
	files, cover = _files(doc, stores) if public and with_files else ([], "")
	pages = (read_cached_pages(doc.item_id) or []) if public and doc.has_page_text else []
	return {
		"item_id": doc.item_id,
		"title": doc.title or doc.item_id,
		"authors": record["creators"],
		"year": doc.year or "",
		"language": doc.language or "",
		"publisher": doc.publisher or "",
		"subjects": record["subjects"],
		"description": frappe.utils.strip_html_tags(doc.description or "")[:2000],
		"files": files,
		"cover": cover,
		"pages": [{"label": p.get("label") or p.get("leaf"), "text": p.get("text") or ""} for p in pages],
		"link": doc.source_url or f"{base_url()}/library/item/{doc.item_id}",
	}


def gather(names: list[str]) -> list[dict]:
	stores: dict = {}
	return [_book(frappe.get_doc("RD Item", n), stores, True) for n in names]


def _total(books: list[dict]) -> int:
	size = 0
	for b in books:
		size += sum(os.path.getsize(p) for _n, p in b["files"] if os.path.isfile(p))
		size += sum(len(p["text"].encode()) for p in b["pages"])
	return size


def _zim(site_dir: str, dest: str, title: str) -> str:
	"""Make a ZIM with zimwriterfs when the server has it; '' when it has not (or it failed)."""
	tool = shutil.which("zimwriterfs")
	if not tool:
		return ""
	try:
		subprocess.run(
			[
				tool,
				"--welcome=index.html",
				"--language=eng",
				f"--title={title[:30]}",
				f"--description={title[:80]}",
				"--creator=Research Desk",
				"--publisher=Research Desk",
				"--name=research-desk",
				"--withoutFTIndex",
				site_dir,
				dest,
			],
			check=True,
			capture_output=True,
			timeout=ZIM_TIMEOUT,
		)
		return dest
	except (subprocess.SubprocessError, OSError):
		return ""


def build(export_name: str, names: list[str]) -> tuple[str, int, str]:
	"""Make the offline copy for an Export; returns (file_url, books written, summary)."""
	if len(names) > MAX_BOOKS:
		frappe.throw(
			_("{0} books are too many for one offline copy: choose up to {1}.").format(len(names), MAX_BOOKS)
		)
	books = gather(names)
	problem = free_problem(_total(books))
	if problem:
		frappe.throw(problem)
	title = portal_title()
	stamp = now_datetime().strftime("%Y-%m-%d")
	intro = _("An offline copy of the library: open index.html. No internet is needed.")
	base = f"offline-copy-{export_name.lower()}"
	dest = os.path.join(folder(), base + ".zip")
	count = offline.write_zip(dest, books, title, intro, stamp, creator=title)
	file_url, extra = f"/private/files/{base}.zip", ""
	zim = ""
	if shutil.which("zimwriterfs"):
		site = os.path.join(folder(), base + "-site")
		shutil.rmtree(site, ignore_errors=True)
		offline.write_folder(site, books, title, intro, stamp, creator=title)
		zim = _zim(site, os.path.join(folder(), base + ".zim"), title)
		shutil.rmtree(site, ignore_errors=True)
		if zim:
			extra = _("; a ZIM file was made too: {0}").format(f"/private/files/{base}.zim")
	for name in (base + ".zip", base + ".zim") if zim else (base + ".zip",):
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": name,
				"file_url": f"/private/files/{name}",
				"attached_to_doctype": "RD Export",
				"attached_to_name": export_name,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
	with_text = sum(1 for b in books if b["pages"])
	return (
		file_url,
		len(books),
		_("{0} books, {1} with their text, {2} files ({3} MB)").format(
			len(books), with_text, count, os.path.getsize(dest) >> 20
		)
		+ (extra or _("; a ZIM needs zimwriterfs (see HOW-TO-MAKE-A-ZIM.txt in the zip)")),
	)


@frappe.whitelist()
def estimate(values) -> dict:
	"""How much an offline copy of these books would hold (before making it)."""
	from sok_resdesk.transfer import select_for_export

	frappe.only_for(STAFF)
	values = frappe.parse_json(values) if isinstance(values, str) else values
	doc = frappe.get_doc({"doctype": "RD Export", **values})
	names = select_for_export(doc)
	books = gather(names[:MAX_BOOKS])
	size = _total(books)
	return {
		"books": len(names),
		"with_files": sum(1 for b in books if b["files"]),
		"with_text": sum(1 for b in books if b["pages"]),
		"details_only": sum(1 for b in books if not b["files"] and not b["pages"]),
		"megabytes": size >> 20,
		"zim": bool(shutil.which("zimwriterfs")),
		"problem": free_problem(size),
	}
