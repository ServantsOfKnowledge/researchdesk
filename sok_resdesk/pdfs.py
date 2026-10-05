"""PDFs of books that aren't on archive.org: their pages as images, and OCR for scans.

A book from a repository or from the library's own folders has a PDF but no page images
served by archive.org. Its pages are drawn from the PDF (core/pdfrender.py): on screen in
*Page & text* and for proofreading, and at 300 dpi for Tesseract. A PDF held elsewhere (a
repository, a book server) is fetched once and kept in ``private/resdesk-pdfs`` up to
Settings → Catalogue → *Space for Downloaded PDFs*; drawn pages are kept beside it.

**Scans without text** (Settings → Catalogue → *Read Scans with OCR*): a book whose PDF has no
text layer is read with Tesseract in the background, every page in the book's languages. The
text is kept in ``private/resdesk-ocr`` (it was made here and can't be fetched again) and is
the book's page text from then on: search inside the book, *Page & text*, proofreading.
"""

from __future__ import annotations

import gzip
import json
import os
import time

import frappe
from frappe import _
from frappe.utils import cint, flt

from sok_resdesk.core import ocr_engine
from sok_resdesk.core.pdfrender import OCR_DPI, VIEW_DPI, RenderError, page_count, render
from sok_resdesk.holding import hold_when_paused

SCAN = "PDF without text (scan)"  # RD Item text_source of a book waiting for OCR


def _dir(name: str) -> str:
	path = frappe.get_site_path("private", name)
	os.makedirs(path, exist_ok=True)
	return path


def _safe(item_id: str) -> str:
	return item_id.replace("/", "_")


# -- the book's PDF ---------------------------------------------------------------------------


def has_pdf(record: dict) -> bool:
	"""Whether pages can be drawn for this book (a record from catalogue.item_to_record)."""
	return bool(
		not record.get("on_archive_org")
		and (record.get("local_pdf") or record.get("from_repository") or record.get("served_from_copy"))
		and record.get("pdf_url")
	)


def pdf_path(item_id: str) -> str | None:
	"""A path on this server to the book's PDF: its own file in a folder source or our
	preservation copy, else a copy fetched from the repository or book server."""
	row = frappe.db.get_value(
		"RD Item",
		item_id,
		["source", "local_pdf", "local_path", "remote_pdf", "served_from_copy"],
		as_dict=True,
	)
	if not row:
		return None
	if row.served_from_copy:
		from sok_resdesk.preservation import copy_pdf

		found = copy_pdf(item_id)
		if found:
			return found[1]
	if row.source == "Local" and row.local_pdf:
		from sok_resdesk.local_source import store_for_item

		store = store_for_item(frappe.get_doc("RD Item", item_id))
		if store is None:
			return None
		if hasattr(store, "file_path"):
			return store.file_path(row.local_path, row.local_pdf)
		return _fetched(item_id, lambda: store.read(row.local_path, row.local_pdf))
	if row.remote_pdf:
		from sok_resdesk.repository import download_pdf

		return _fetched(item_id, lambda: download_pdf(row.remote_pdf))
	return None


def _fetched(item_id: str, fetch) -> str | None:
	path = os.path.join(_dir("resdesk-pdfs"), f"{_safe(item_id)}.pdf")
	if os.path.exists(path):
		os.utime(path)  # recently used: kept longest
		return path
	data = fetch()
	if not data:
		return None
	tmp = f"{path}.{os.getpid()}.tmp"
	with open(tmp, "wb") as f:
		f.write(data)
	os.replace(tmp, path)
	_prune(os.path.dirname(path))
	return path


def _prune(folder: str) -> None:
	"""Keep downloaded PDFs within Settings → Space for Downloaded PDFs, least used first out."""
	cap = flt(frappe.db.get_single_value("RD Settings", "pdf_space_gb") or 5) * 1024**3
	files = []
	for name in os.listdir(folder):
		if name.endswith(".pdf"):
			st = os.stat(os.path.join(folder, name))
			files.append((st.st_mtime, st.st_size, name))
	total = sum(s for _m, s, _n in files)
	for _mtime, size, name in sorted(files):
		if total <= cap:
			break
		try:
			os.remove(os.path.join(folder, name))
			total -= size
		except OSError:
			pass


def page_jpeg(item_id: str, leaf: int) -> bytes:
	"""Page `leaf` for the screen (kept once drawn)."""
	cached = os.path.join(
		_dir("resdesk-page-images"), _safe(item_id)[:2].lower(), _safe(item_id), f"{leaf}.jpg"
	)
	if os.path.exists(cached):
		with open(cached, "rb") as f:
			return f.read()
	path = pdf_path(item_id)
	if not path:
		raise RenderError(_("This book's PDF can't be reached."))
	data = render(path, leaf, VIEW_DPI, grey=False, fmt="jpeg")
	os.makedirs(os.path.dirname(cached), exist_ok=True)
	with open(cached, "wb") as f:
		f.write(data)
	return data


def page_png(item_id: str, leaf: int) -> bytes:
	"""Page `leaf` at 300 dpi in grey, for Tesseract."""
	path = pdf_path(item_id)
	if not path:
		raise ocr_engine.OcrError(_("This book's PDF can't be reached."))
	try:
		return render(path, leaf, OCR_DPI, grey=True, fmt="png")
	except RenderError as e:
		raise ocr_engine.OcrError(str(e)) from e


def forget_pages(item_id: str) -> None:
	"""Drop the drawn pages of a book (its PDF changed)."""
	import shutil

	folder = os.path.join(_dir("resdesk-page-images"), _safe(item_id)[:2].lower(), _safe(item_id))
	shutil.rmtree(folder, ignore_errors=True)
	try:
		os.remove(os.path.join(_dir("resdesk-pdfs"), f"{_safe(item_id)}.pdf"))
	except OSError:
		pass


# -- text read here with OCR ---------------------------------------------------------------


def _ocr_path(item_id: str) -> str:
	return os.path.join(_dir("resdesk-ocr"), _safe(item_id)[:2].lower(), f"{_safe(item_id)}.json.gz")


def read_ocr_pages(item_id: str) -> list[dict] | None:
	path = _ocr_path(item_id)
	if not os.path.exists(path):
		return None
	try:
		with gzip.open(path, "rt", encoding="utf-8") as f:
			return json.load(f)
	except (OSError, ValueError):
		return None


def write_ocr_pages(item_id: str, pages: list[dict]) -> None:
	path = _ocr_path(item_id)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = f"{path}.tmp"
	with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
		json.dump(pages, f, ensure_ascii=False)
	os.replace(tmp, path)


def ocr_on() -> bool:
	value = frappe.db.get_single_value("RD Settings", "ocr_scans")
	return True if value is None else bool(cint(value))


def queue_ocr(item_id: str) -> bool:
	"""Read a scan with OCR in the background (when Settings say so and Tesseract is here)."""
	from sok_resdesk.reocr import _state

	if not ocr_on():
		return False
	if not ocr_engine.available():
		_state(item_id, _("waiting for OCR: Tesseract isn't installed (Server → Requirements)"))
		return False
	_state(item_id, _("waiting to be read with OCR"))
	frappe.enqueue(
		"sok_resdesk.pdfs.ocr_book",
		queue="long",
		timeout=12 * 3600,
		job_id=f"resdesk-ocr-{item_id}",
		deduplicate=True,
		enqueue_after_commit=True,
		item_id=item_id,
	)
	return True


@hold_when_paused("long")
def ocr_book(item_id: str) -> dict:
	"""Read every page of a scan with Tesseract; its text becomes the book's page text."""
	from pypdf import PdfReader

	from sok_resdesk.reocr import _state, engine_name, models_for

	path = pdf_path(item_id)
	if not path:
		_state(item_id, _("not read: its PDF can't be reached"))
		return {"read": 0}
	try:
		models = models_for(item_id)
	except ocr_engine.OcrError as e:
		_state(item_id, _("not read: {0}").format(str(e)[:120]))
		return {"read": 0}
	try:
		labels = list(PdfReader(path).page_labels)
	except Exception:
		labels = []
	count, pages, failed, started = page_count(path), [], 0, time.monotonic()
	for leaf in range(count):
		if frappe.cache.get_value("resdesk:stop-background"):
			_state(item_id, _("stopped at page {0}: read again from Re-OCR").format(leaf + 1))
			return {"read": leaf, "stopped": True}
		if leaf % 10 == 0:
			_state(item_id, _("reading with OCR: page {0} of {1}").format(leaf + 1, count))
		try:
			text = ocr_engine.read_page(page_png(item_id, leaf), None, models)["text"]
		except ocr_engine.OcrError:
			text, failed = "", failed + 1
		label = labels[leaf] if leaf < len(labels) else ""
		pages.append({"leaf": leaf, "label": "" if label == str(leaf + 1) else label, "text": text})
	write_ocr_pages(item_id, pages)
	_use_text(item_id, pages, engine_name(models))
	_state(
		item_id,
		_("read with OCR: {0} pages in {1} minutes").format(count, round((time.monotonic() - started) / 60))
		+ (_(", {0} pages not read").format(failed) if failed else ""),
	)
	return {"read": count, "failed": failed}


def _use_text(item_id: str, pages: list[dict], engine: str) -> None:
	"""Make OCR'd pages the book's text: the catalogue, the cache, search."""
	from sok_resdesk.catalogue import item_to_record
	from sok_resdesk.ingest import PAGE_ORDER, cache_enabled, write_cached_pages
	from sok_resdesk.pagetext import apply
	from sok_resdesk.search import SearchError, index_record, quality_fields

	has_text = any(p["text"].strip() for p in pages)
	restricted = frappe.db.get_value("RD Item", item_id, "access_status") == "Restricted"
	if cache_enabled():
		write_cached_pages(item_id, pages)
	frappe.db.set_value(
		"RD Item",
		item_id,
		{
			"has_page_text": int(has_text and not restricted),
			"has_fulltext": int(has_text and not restricted),
			"text_source": f"OCR here ({engine})"[:140],
			"page_count": len(pages),
			"page_order": PAGE_ORDER,
			**quality_fields(pages),
		},
		update_modified=False,
	)
	frappe.db.commit()
	if not has_text or restricted:
		return
	try:
		record = item_to_record(frappe.get_doc("RD Item", item_id))
		index_record(record, apply(item_id, pages), replace_pages=True)
	except SearchError as e:
		frappe.log_error("Research Desk: OCR'd text not indexed", f"{item_id}: {e}")
	frappe.db.commit()


def daily() -> None:
	"""Scans still waiting for OCR (a job lost in a restart, OCR switched on later): queue some."""
	if not ocr_on() or not ocr_engine.available():
		return
	waiting = frappe.get_all(
		"RD Item",
		filters={"text_source": SCAN, "published": 1},
		pluck="name",
		limit=200,
		order_by="creation asc",
	)
	for name in waiting:
		if read_ocr_pages(name) is None:
			queue_ocr(name)


@frappe.whitelist(methods=["POST"])
def ocr_now(item_id: str) -> dict:
	"""Book form → Read with OCR: read a scan's pages now (in the background)."""
	frappe.only_for(("System Manager", "ResDesk Manager", "ResDesk Cataloguer"))
	if not ocr_engine.available():
		frappe.throw(_("The OCR engine (Tesseract) isn't installed on this server."))
	if not pdf_path(item_id):
		frappe.throw(_("This book has no PDF here to read."))
	frappe.enqueue(
		"sok_resdesk.pdfs.ocr_book",
		queue="long",
		timeout=12 * 3600,
		job_id=f"resdesk-ocr-{item_id}",
		deduplicate=True,
		item_id=item_id,
	)
	from sok_resdesk.reocr import _state

	_state(item_id, _("waiting to be read with OCR"))
	return {"queued": True}
