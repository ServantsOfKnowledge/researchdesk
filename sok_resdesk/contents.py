"""Tables of contents of the books: read from the contents pages, checked by a person, then published.

Staff read one book's contents from its form; an admin can run it over many books (a background
job). What is read is only ever a draft (RD Book Contents): a librarian or metadata manager checks
it, mends it and publishes it, and only then do readers see it on the book's page. The rules for
finding and reading the pages are in core/contents.py.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import access, assistant
from sok_resdesk.core import contents as rules
from sok_resdesk.core import llm
from sok_resdesk.holding import hold_when_paused

DOCTYPE = "RD Book Contents"
BATCH = 50  # books to a background job
RUN = "resdesk:contents-run:"  # progress of one bulk run, in the cache


def _staff_only() -> None:
	if not access.is_staff():
		frappe.throw(_("Only staff can read the contents of books."), frappe.PermissionError)


def extract_now(item_id: str, reread: bool = False, user: str | None = None) -> dict:
	"""Read one book's contents pages into a draft. A published list is left alone (withdraw it first).

	reread: the contents pages are read again with the OCR engine first (the book's own text is not
	changed): for a list that came out unclear. Returns {"status", "entries", "message"}."""
	from sok_resdesk.ingest import fetch_pages

	existing = frappe.db.get_value(DOCTYPE, item_id, "status")
	if existing == "Published":
		return {
			"status": existing,
			"entries": 0,
			"message": _("Its contents are published: withdraw them first."),
		}
	pages = fetch_pages(item_id) if frappe.db.get_value("RD Item", item_id, "has_page_text") else []
	if not pages:
		return {
			"status": "",
			"entries": 0,
			"message": _("This book has no page text to read the contents from."),
		}
	texts = {p["leaf"]: p.get("text") or "" for p in pages}
	found = rules.find_pages(pages)
	leaves = found["leaves"]
	if reread:
		leaves = leaves or _likeliest(pages)
		texts.update(_ocr(item_id, leaves))
	entries = rules.parse([texts[leaf] for leaf in leaves]) if leaves else []
	judged = rules.quality(entries, sum(rules.density(texts[leaf])[1] for leaf in leaves))
	helped = False
	if (judged["unclear"] or not entries) and assistant.enabled("contents"):
		better, tried = _from_assistant(pages, texts, leaves)
		if len(better) > len(entries):
			entries, leaves, helped = better, tried, True
			judged = rules.quality(entries, len(entries))  # every line the model gave is an entry
	if not leaves or not entries:
		return {"status": "", "entries": 0, "message": _("No contents page was found among the first pages.")}
	labels = {p["leaf"]: p.get("label") or "" for p in pages}
	entries = rules.leaves_for(entries, labels, texts, after=max(leaves))
	doc = frappe.get_doc(DOCTYPE, item_id) if existing else frappe.new_doc(DOCTYPE)
	doc.item = item_id
	doc.status = "Needs a Look" if judged["unclear"] or not entries else "Draft"
	doc.quality = judged["score"]
	doc.why = judged["why"]
	doc.contents_pages = ", ".join(str(leaf + 1) for leaf in leaves)
	doc.reread = 1 if reread else 0
	doc.by_assistant = 1 if helped else 0
	doc.extracted_on = now_datetime()
	doc.extracted_by = user or frappe.session.user
	doc.set(
		"entries",
		[
			{
				"title": e["title"],
				"page_label": e["page"],
				"image_no": (e["leaf"] + 1) if e["leaf"] is not None else None,
				"level": min(e["level"], 4),
			}
			for e in entries
		],
	)
	doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
	return {
		"status": doc.status,
		"entries": len(entries),
		"message": _("{0} headings read; {1}.").format(
			len(entries),
			_("it needs a look") if doc.status == "Needs a Look" else _("it is a draft to check"),
		),
	}


def _from_assistant(pages: list[dict], texts: dict, leaves: list[int]) -> tuple[list[dict], list[int]]:
	"""The model's reading of the contents pages (those found, else the likeliest front pages). Only
	entries the pages support survive (core/llm.py); a person still checks the draft."""
	tried = leaves or _likeliest(pages)
	if not tried:
		return [], []
	shown = [texts[leaf] for leaf in tried]
	system, user = llm.contents_prompt(shown)
	return llm.contents_entries(assistant.ask(system, user, 2000), "\n".join(shown)), tried


def _likeliest(pages: list[dict]) -> list[int]:
	"""With no contents heading found, the front pages with most lines that look like entries."""
	front = pages[: max(12, min(rules.FRONT_PAGES, len(pages) // 8))]
	ranked = sorted(front, key=lambda p: rules.density(p.get("text") or "")[0], reverse=True)
	return sorted(p["leaf"] for p in ranked[:2] if rules.density(p.get("text") or "")[0] >= 2)


def _ocr(item_id: str, leaves: list[int]) -> dict[int, str]:
	"""The OCR engine's own reading of these pages (a page it cannot read keeps the text it had)."""
	from sok_resdesk import reocr

	if not reocr.ocr_engine.available():
		return {}
	out = {}
	for leaf in leaves:
		try:
			out[leaf] = reocr.read(item_id, leaf)["text"]
		except Exception:
			frappe.log_error(
				title=f"Research Desk: contents page {leaf} of {item_id} could not be read again"
			)
	return out


@frappe.whitelist(methods=["POST"])
def extract(item_id: str, reread: int = 0) -> dict:
	"""Read one book's contents (staff). With reread, in the background: OCR takes a few seconds a page."""
	_staff_only()
	if not frappe.db.exists("RD Item", item_id):
		frappe.throw(_("No such book."), frappe.DoesNotExistError)
	if cint(reread):
		frappe.enqueue(
			"sok_resdesk.contents.extract_job",
			queue="short",
			timeout=900,
			item_id=item_id,
			user=frappe.session.user,
		)
		return {"queued": 1, "message": _("Reading the contents pages again; the draft updates in a minute.")}
	return extract_now(item_id, False, frappe.session.user)


def extract_job(item_id: str, user: str) -> None:
	extract_now(item_id, True, user)


@frappe.whitelist(methods=["POST"])
def bulk(names=None, filters=None, everything: int = 0) -> dict:
	"""Read the contents of many books in the background (managers and super admins). Books that already
	have a list, or have no page text, are skipped; the results are drafts for librarians to check."""
	if not access.is_admin():
		frappe.throw(_("Only managers can run this over many books."), frappe.PermissionError)
	chosen = access.select_items(names, filters, None, None, None, None, bool(cint(everything)))
	todo = [n for n in chosen if not frappe.db.exists(DOCTYPE, n)]
	todo = [n for i in range(0, len(todo), 1000) for n in _with_text(todo[i : i + 1000])]
	if not todo:
		return {
			"count": 0,
			"message": _("Nothing to read: those books have no page text, or already have a list."),
		}
	parts = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
	run = frappe.generate_hash(length=10)
	frappe.cache().set(_key(run, "left"), len(parts), ex=86400)
	frappe.cache.set_value(RUN + run, {"user": frappe.session.user, "total": len(todo)}, expires_in_sec=86400)
	for part in parts:
		frappe.enqueue(
			"sok_resdesk.contents.extract_batch",
			queue="long",
			timeout=6 * 3600,
			names=part,
			run=run,
			user=frappe.session.user,
		)
	return {
		"count": len(todo),
		"message": _(
			"Reading the contents of {0} books in the background. You get an alert when it is done."
		).format(len(todo)),
	}


def _with_text(names: list[str]) -> list[str]:
	return frappe.get_all("RD Item", filters={"name": ("in", names), "has_page_text": 1}, pluck="name")


@hold_when_paused("long")
def extract_batch(names: list[str], run: str, user: str) -> None:
	counts = {"drafts": 0, "look": 0, "none": 0}
	for name in names:
		if frappe.cache.get_value("resdesk:stop-background"):
			break  # "Stop everything" on the Background Jobs page
		try:
			result = extract_now(name, False, user)
		except Exception:
			frappe.log_error(title=f"Research Desk: contents of {name} could not be read")
			continue
		counts["drafts" if result["status"] == "Draft" else "look" if result["status"] else "none"] += 1
		frappe.db.commit()
	_batch_done(run, counts)


def _key(run: str, name: str) -> str:
	return frappe.cache().make_key(f"{RUN}{run}:{name}")


def _batch_done(run: str, counts: dict) -> None:
	"""Add this batch to the run's totals; the last batch tells the person who started it."""
	cache = frappe.cache()
	for name, n in counts.items():
		cache.incrby(_key(run, name), n)
	if cache.incrby(_key(run, "left"), -1) <= 0:
		_tell(run, frappe.cache.get_value(RUN + run) or {})


def _tell(run: str, state: dict) -> None:
	cache = frappe.cache()

	def n(name: str) -> int:
		return int(cache.get(_key(run, name)) or 0)

	subject = _(
		"Contents read for {0} books: {1} drafts to check, {2} that need a look, {3} with no contents page found."
	).format(state.get("total", 0), n("drafts"), n("look"), n("none"))
	user = state.get("user")
	if not user or user == "Guest":
		return
	try:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": DOCTYPE,
				"subject": subject,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Research Desk: could not tell who ran the contents job")


@frappe.whitelist(methods=["POST"])
def set_status(item_id: str, status: str) -> dict:
	"""Publish a list, reject it, or take a published one back to a draft (staff)."""
	_staff_only()
	if status not in ("Published", "Rejected", "Draft"):
		frappe.throw(_("Choose Published, Rejected or Draft."))
	doc = frappe.get_doc(DOCTYPE, item_id)
	if status == "Published" and not [r for r in doc.entries if r.title]:
		frappe.throw(_("There are no headings to publish."))
	doc.status = status
	doc.reviewed_by = frappe.session.user
	doc.published_on = now_datetime() if status == "Published" else None
	doc.save(ignore_permissions=True)
	return {"status": doc.status}


def published(item_id: str) -> list[dict]:
	"""The headings readers see on the book's page: [{title, page, image_no, level}] (none unless published)."""
	if frappe.db.get_value(DOCTYPE, item_id, "status") != "Published":
		return []
	return [
		{
			"title": r.title,
			"page": r.page_label,
			"leaf": (r.image_no - 1) if r.image_no else None,
			"level": r.level,
		}
		for r in frappe.get_doc(DOCTYPE, item_id).entries
		if r.title
	]
