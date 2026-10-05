"""Machine drafts of transcripts (Item → Draft the Transcript / Draft the Text of the Leaves).

A recording's speech is turned into text segments, a manuscript's leaves are read by a handwriting
engine, both on the library's own server and in the background. The result is saved as *Machine*
page versions, which people proofread: a draft never replaces a person's work, a second run
replaces only earlier machine drafts, and drafts are never shared as ground truth.
See core/draft.py for the engines.
"""

from __future__ import annotations

import os
import tempfile

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import features, pagetext
from sok_resdesk.core import draft
from sok_resdesk.core import media as media_core

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
SOURCE = "Machine draft"


def _setting(name: str, default: str = "") -> str:
	return (frappe.db.get_single_value("RD Settings", name) or default).strip()


@frappe.whitelist()
def status() -> dict:
	"""What this server can draft with."""
	frappe.only_for(STAFF)
	return {
		"speech": draft.asr_engine(),
		"handwriting": draft.htr_engines(),
		"speech_model": _setting("draft_asr_model", "small"),
		"handwriting_engine": _setting("draft_htr_engine", "Tesseract"),
	}


def _enqueue(method: str, item: str, **kw) -> dict:
	frappe.enqueue(
		f"sok_resdesk.drafts.{method}",
		queue="long",
		timeout=24 * 3600,
		item=item,
		user=frappe.session.user,
		enqueue_after_commit=True,
		**kw,
	)
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
@features.needs("proofreading")
def draft_transcript(item: str) -> dict:
	"""Draft a recording's transcript from its speech, in the background."""
	frappe.only_for(STAFF)
	doc = frappe.get_doc("RD Item", item)
	if not doc.media_files or doc.source != "Local":
		frappe.throw(_("Only a recording whose file is held here can be drafted."))
	if not draft.asr_engine():
		frappe.throw(_("This server has no speech engine: install faster-whisper (pip) or whisper."))
	return _enqueue("run_transcript", item)


@frappe.whitelist(methods=["POST"])
@features.needs("proofreading")
def draft_leaves(item: str, leaves: str = "") -> dict:
	"""Draft the text of a book's leaves by handwriting recognition, in the background.
	`leaves`: leaf numbers from 0, e.g. "0-9,14"; empty for all."""
	frappe.only_for(STAFF)
	from sok_resdesk.pdfs import can_draw

	doc = frappe.get_doc("RD Item", item)
	if not can_draw({**doc.as_dict(), "on_archive_org": doc.on_archive_org}):
		frappe.throw(_("This book's pages cannot be drawn here to be read."))
	engine = _setting("draft_htr_engine", "Tesseract").lower()
	if engine not in draft.htr_engines():
		frappe.throw(_("{0} is not installed on this server.").format(engine.title()))
	return _enqueue("run_leaves", item, leaves=leaves)


def leaf_numbers(spec: str, count: int) -> list[int]:
	"""'0-9,14' → [0..9, 14], inside the book; '' → every leaf."""
	if not (spec or "").strip():
		return list(range(count))
	out: list[int] = []
	for part in spec.split(","):
		a, _, b = part.strip().partition("-")
		if a.strip().isdigit():
			lo = int(a)
			hi = int(b) if b.strip().isdigit() else lo
			out += [n for n in range(lo, min(hi, count - 1) + 1) if n not in out]
	return out


def _save(item: str, leaf: int, text: str, engine: str, label: str = "", versions=None) -> bool:
	"""A machine version, unless a person has worked on the page. True when saved. `versions`:
	the book's current versions, read once by the caller."""
	now = (versions if versions is not None else pagetext.current(item)).get(leaf)
	if not text.strip() or not draft.may_draft(now.status if now else None):
		return False
	pagetext.save(item, leaf, text, SOURCE, "Machine", engine=engine, page_label=label, reindex=False)
	return True


def _finish(item: str, saved: int) -> None:
	"""Search follows the drafts, and the book can be read as text."""
	if not saved:
		return
	if frappe.db.get_value("RD Item", item, "access_status") != "Restricted":
		frappe.db.set_value("RD Item", item, {"has_page_text": 1, "has_fulltext": 1}, update_modified=False)
	from sok_resdesk.ingest import fetch_pages
	from sok_resdesk.search import quality_fields, reindex_pages

	pages = fetch_pages(item)
	frappe.db.set_value("RD Item", item, quality_fields(pages), update_modified=False)
	try:
		reindex_pages(item, pages)
	except Exception:
		frappe.log_error(title=f"Research Desk: drafts of {item} not indexed")


def _notify(user: str | None, subject: str) -> None:
	if not user:
		return
	try:
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": subject}
		).insert(ignore_permissions=True)
	except Exception:
		pass


def run_transcript(item: str, user: str | None = None) -> int:
	"""The job: speech to text over the recording, into its segments."""
	doc = frappe.get_doc("RD Item", item)
	model = _setting("draft_asr_model", "small")
	try:
		from sok_resdesk.local_source import store_for_item

		store = store_for_item(doc)
		names = store.media_files(doc.local_path) if store else []
		path = store.file_path(doc.local_path, names[0]) if names else None
		if not path:
			raise draft.DraftError("The recording's file cannot be reached.")
		cues = draft.transcribe(path, doc.language or "", model)
		slots = media_core.times_from(doc.leaf_times)
		if slots:
			order = sorted(slots)
			texts = draft.fill_segments([slots[n] for n in order], cues)
			labels = {n: media_core.fmt(slots[n][0]) for n in order}
			items = list(zip(order, texts, strict=True))
		else:
			segs = media_core.segments(cues)
			doc.db_set({"leaf_times": media_core.times_json(segs), "page_count": len(segs)})
			items = [(n, s["text"], media_core.fmt(s["start"])) for n, s in enumerate(segs)]
			labels = {}
		saved = 0
		engine = f"{draft.asr_engine()} {model}"
		versions = pagetext.current(item)
		for entry in items:
			leaf, text = entry[0], entry[1]
			label = entry[2] if len(entry) > 2 else labels.get(leaf, "")
			saved += _save(item, leaf, text, engine, label, versions)
		_finish(item, saved)
		_notify(user, _("Draft transcript of {0}: {1} segments (to be proofread)").format(doc.title, saved))
		frappe.db.commit()
		return saved
	except draft.DraftError as e:
		frappe.db.rollback()
		_notify(user, _("Draft of {0} failed: {1}").format(doc.title, str(e)[:200]))
		frappe.db.commit()
		return 0


def _read_leaf(item: str, leaf: int, engine: str, model: str) -> str:
	if engine == "kraken":
		from sok_resdesk.pdfs import page_png

		with tempfile.TemporaryDirectory() as tmp:
			image = os.path.join(tmp, "leaf.png")
			with open(image, "wb") as f:
				f.write(page_png(item, leaf))
			return draft.kraken_read(image, model)
	from sok_resdesk import reocr

	return reocr.read(item, leaf)["text"]


def run_leaves(item: str, user: str | None = None, leaves: str = "") -> int:
	"""The job: handwriting recognition over the leaves nobody has worked on."""
	doc = frappe.get_doc("RD Item", item)
	engine = _setting("draft_htr_engine", "Tesseract").lower()
	model = _setting("draft_htr_model")
	saved = failed = 0
	versions = pagetext.current(item)
	for n, leaf in enumerate(leaf_numbers(leaves, cint(doc.page_count))):
		try:
			text = _read_leaf(item, leaf, engine, model)
		except Exception as e:  # one leaf that cannot be read must not stop the rest
			failed += 1
			if failed == 1:
				frappe.log_error(title=f"Research Desk: draft of {item} leaf {leaf}: {str(e)[:100]}")
			continue
		label = engine if engine == "tesseract" else f"kraken {os.path.basename(model)}"
		saved += _save(item, leaf, text, label, versions=versions)
		if n % 20 == 19:
			frappe.db.commit()
	_finish(item, saved)
	_notify(
		user,
		_("Draft text of {0}: {1} leaves read{2} (to be proofread)").format(
			doc.title, saved, _(", {0} could not be read").format(failed) if failed else ""
		),
	)
	frappe.db.commit()
	return saved
