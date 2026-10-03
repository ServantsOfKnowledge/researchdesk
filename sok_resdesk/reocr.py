"""Re-OCR: reading page images again with Tesseract and its Indic models (core/ocr_engine.py).

* **One page, with zones**, from Page & text → Proofread: the proofreader draws the parts of the
  page to read (columns, headings, side notes) in reading order, and the result comes back to
  them to check before they save it.
* **Whole books**, in the background (book form → Re-OCR, or Items → Re-OCR the worst books):
  each page is read with a zone layout (whole page, two columns…), and the new text is kept only
  where it scores better than the text the page has (core/ocrquality.py). Pages people have
  proofread are never touched.

Page images come from archive.org (one request per page, at the pace set in Settings).
"""

from __future__ import annotations

import subprocess

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk.core import ocr_engine, ocrquality
from sok_resdesk.core import zones as zn
from sok_resdesk.holding import hold_when_paused

MANAGERS = ("System Manager", "ResDesk Manager")
KEEP_IF_BETTER_BY = 5  # points of OCR quality a machine text must gain to replace the page's text
RESULT_KEY = "resdesk:ocr-result:"


def engine_name(models: str) -> str:
	try:
		out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=20)
		version = (out.stdout or out.stderr).splitlines()[0].strip()
	except Exception:
		version = "tesseract"
	return f"{version} ({models})"


def page_image(item_id: str, leaf: int) -> bytes:
	from sok_resdesk.api import page_image_url
	from sok_resdesk.catalogue import get_record
	from sok_resdesk.ingest import client

	record = get_record(item_id, published_only=False, check_access=False)
	url = page_image_url(record, leaf) if record else ""
	if not url:
		raise ocr_engine.OcrError(
			_("This book has no page images to read (only books on archive.org, for now).")
		)
	resp = client()._get(url)
	if resp.status_code != 200 or not resp.content:
		raise ocr_engine.OcrError(
			_("archive.org did not send page image {0} ({1}).").format(leaf, resp.status_code)
		)
	return resp.content


def models_for(item_id: str) -> str:
	language = frappe.db.get_value("RD Item", item_id, "language") or ""
	return ocr_engine.models_for(language)


def read(item_id: str, leaf: int, zones: list | None = None) -> dict:
	models = models_for(item_id)
	result = ocr_engine.read_page(page_image(item_id, leaf), zones, models)
	result["engine"] = engine_name(models)
	result["quality"] = ocrquality.page_quality(result["text"])["score"]
	return result


# -- one page, for a proofreader --------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def ocr_page(item_id: str, leaf: int, zones=None) -> dict:
	"""Read one page (in its zones) in the background; ocr_result says when it is ready."""
	from sok_resdesk.pagetext import _check

	_check(item_id)
	if not ocr_engine.available():
		frappe.throw(_("The OCR engine (Tesseract) isn't installed on this server."))
	zones = zn.clean(zones) if zones else []
	key = frappe.generate_hash(length=12)
	frappe.cache.set_value(RESULT_KEY + key, {"status": "queued"}, expires_in_sec=3600)
	frappe.enqueue(
		"sok_resdesk.reocr.ocr_page_job",
		queue="short",
		timeout=600,
		key=key,
		item_id=item_id,
		leaf=cint(leaf),
		zones=zones,
		user=frappe.session.user,
	)
	return {"key": key}


def ocr_page_job(key: str, item_id: str, leaf: int, zones: list, user: str) -> None:
	frappe.cache.set_value(RESULT_KEY + key, {"status": "running"}, expires_in_sec=3600)
	try:
		r = read(item_id, leaf, zones)
		out = {
			"status": "done",
			"text": r["text"],
			"quality": r["quality"],
			"engine": r["engine"],
			"zones": [p["text"] for p in r["zones"]],
		}
	except ocr_engine.OcrError as e:
		out = {"status": "failed", "error": str(e)}
	except Exception as e:
		frappe.log_error(title=f"Research Desk: OCR of {item_id} page {leaf} failed")
		out = {"status": "failed", "error": str(e)[:300]}
	out["user"] = user
	frappe.cache.set_value(RESULT_KEY + key, out, expires_in_sec=3600)


@frappe.whitelist(methods=["GET"])
def ocr_result(key: str) -> dict:
	out = frappe.cache.get_value(RESULT_KEY + key) or {"status": "gone"}
	if out.get("user") and out["user"] != frappe.session.user:
		raise frappe.PermissionError
	return out


# -- whole books, in the background ----------------------------------------------------------------


def _state(item_id: str, text: str) -> None:
	frappe.db.set_value("RD Item", item_id, "reocr_state", text[:140], update_modified=False)
	frappe.db.commit()


@hold_when_paused("long")
def reocr_book(item_id: str, preset: str = "Whole page") -> dict:
	"""Read every page of a book again; keep the new text where it is better. Returns counts."""
	from sok_resdesk.ingest import fetch_pages
	from sok_resdesk.pagetext import HUMAN, current, save

	zones = zn.presets().get(preset) or zn.presets()["Whole page"]
	models = models_for(item_id)
	engine = engine_name(models)
	pages = {p["leaf"]: p for p in fetch_pages(item_id)}
	versions = current(item_id)
	last = max([cint(frappe.db.get_value("RD Item", item_id, "page_count")) - 1, *pages] or [0])
	read_count = improved = failed = 0
	for leaf in range(0, last + 1):
		if frappe.cache.get_value("resdesk:stop-background"):
			break
		if leaf in versions and versions[leaf].status in HUMAN:
			continue  # a person's work is never replaced by a machine's
		if read_count % 10 == 0:
			_state(
				item_id, _("reading page {0} of {1}: {2} better so far").format(leaf + 1, last + 1, improved)
			)
		try:
			result = ocr_engine.read_page(page_image(item_id, leaf), zones, models)
		except ocr_engine.OcrError:
			failed += 1
			continue
		read_count += 1
		old = (pages.get(leaf) or {}).get("text") or ""
		new_score = ocrquality.page_quality(result["text"])["score"] or 0
		old_score = ocrquality.page_quality(old)["score"] if old.strip() else None
		if result["text"].strip() and (old_score is None or new_score >= old_score + KEEP_IF_BETTER_BY):
			save(
				item_id,
				leaf,
				result["text"],
				"Re-OCR",
				"Machine",
				zones,
				engine,
				(pages.get(leaf) or {}).get("label") or "",
				reindex=False,
			)
			improved += 1
		frappe.db.commit()
	# search and the book's quality follow once, at the end
	from sok_resdesk.pagetext import _after_change
	from sok_resdesk.search import reindex_pages

	_after_change(item_id, 0, reindex=False)
	if improved:
		new_pages = fetch_pages(item_id)
		from sok_resdesk.search import quality_fields

		frappe.db.set_value("RD Item", item_id, quality_fields(new_pages), update_modified=False)
		changed = {leaf for leaf, v in current(item_id).items() if v.source == "Re-OCR"}
		try:
			reindex_pages(item_id, [p for p in new_pages if p["leaf"] in changed])
		except Exception:
			frappe.log_error(title=f"Research Desk: re-OCR of {item_id} not re-indexed")
	_state(
		item_id,
		_("{0} pages read with {1}, {2} better (kept), {3} not read").format(
			read_count, preset.lower(), improved, failed
		),
	)
	return {"read": read_count, "improved": improved, "failed": failed}


@hold_when_paused("long")
def reocr_books(names: list[str], preset: str = "Whole page") -> None:
	"""One book at a time, then the rest in a new job (so a long list never fills the queue)."""
	if not names:
		return
	try:
		reocr_book(names[0], preset)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Research Desk: re-OCR of {names[0]} failed")
		_state(names[0], _("failed: see the Error Log"))
	if names[1:]:
		frappe.enqueue(
			"sok_resdesk.reocr.reocr_books", queue="long", timeout=6 * 3600, names=names[1:], preset=preset
		)


def _queue(names: list[str], preset: str) -> int:
	if preset not in zn.presets():
		frappe.throw(_("Choose a layout: {0}").format(", ".join(zn.presets())))
	if not ocr_engine.available():
		frappe.throw(_("The OCR engine (Tesseract) isn't installed on this server."))
	for name in names:
		_state(name, _("waiting to be read again"))
	frappe.enqueue(
		"sok_resdesk.reocr.reocr_books", queue="long", timeout=6 * 3600, names=names, preset=preset
	)
	return len(names)


@frappe.whitelist(methods=["POST"])
def enqueue_book(item_id: str, preset: str = "Whole page") -> dict:
	frappe.only_for(MANAGERS)
	_queue([item_id], preset)
	return {"message": _("{0} is being read again in the background.").format(item_id)}


@frappe.whitelist(methods=["POST"])
def enqueue_worst(count: int = 20, preset: str = "Whole page") -> dict:
	"""The books with the worst OCR quality (on archive.org, not re-read yet) first."""
	frappe.only_for(MANAGERS)
	names = frappe.get_all(
		"RD Item",
		filters={"ocr_quality": (">", 0), "on_archive_org": 1, "reocr_state": ("is", "not set")},
		pluck="name",
		order_by="ocr_quality asc",
		limit=max(1, min(cint(count), 500)),
	)
	n = _queue(names, preset) if names else 0
	return {"message": _("{0} books are being read again, the worst first.").format(n)}


@frappe.whitelist(methods=["GET"])
def engine_status() -> dict:
	"""For the Desk: whether OCR can run here, and with which language models."""
	have = ocr_engine.available()
	return {"installed": bool(have), "models": have, "presets": list(zn.presets())}
