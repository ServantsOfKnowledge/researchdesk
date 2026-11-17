"""Catalogue details read from a book's title page and imprint page: read, checked by a person, applied.

Staff read one book from its form; an admin can run it over many books (a background job). What is
read is only ever a draft (RD Metadata Suggestion): a librarian or metadata manager checks each
detail and applies it, and only then does the book change. An applied detail is a reviewed edit, so
the book keeps it through later ingests and it goes out with the book's other metadata to the systems
it is pushed to. The rules for reading the pages are in core/frontmatter.py.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk import access
from sok_resdesk.core import frontmatter as rules
from sok_resdesk.holding import hold_when_paused

DOCTYPE = "RD Metadata Suggestion"
BATCH = 50  # books to a background job
RUN = "resdesk:frontmatter-run:"  # progress of one bulk run, in the cache


def _staff_only() -> None:
	if not access.is_staff():
		frappe.throw(_("Only staff can read details from the pages of books."), frappe.PermissionError)


def extract_now(item_id: str, user: str | None = None) -> dict:
	"""Read the title and imprint pages of one book into a draft. A draft that was already checked
	(Applied) is left alone. Returns {"status", "entries", "message"}."""
	from sok_resdesk.ingest import fetch_pages

	existing = frappe.db.get_value(DOCTYPE, item_id, "status")
	if existing == "Applied":
		return {"status": existing, "entries": 0, "message": _("Its details were already applied.")}
	book = frappe.db.get_value("RD Item", item_id, ["has_page_text", "lock_metadata"], as_dict=True)
	pages = fetch_pages(item_id) if book and book.has_page_text else []
	if not pages:
		return {"status": "", "entries": 0, "message": _("This book has no page text to read details from.")}
	current = frappe.db.get_value("RD Item", item_id, list(rules.FIELDS), as_dict=True)
	found = [f for f in rules.read(pages) if rules.is_new(f["field"], f["value"], current[f["field"]])]
	found += _from_assistant(pages, current, {f["field"] for f in found})
	if not found:
		return {"status": "", "entries": 0, "message": _("Nothing new was found on the first pages.")}
	doc = frappe.get_doc(DOCTYPE, item_id) if existing else frappe.new_doc(DOCTYPE)
	doc.item = item_id
	doc.status = "Draft"
	doc.extracted_on = now_datetime()
	doc.extracted_by = user or frappe.session.user
	doc.set(
		"details",
		[
			{
				"field": f["field"],
				"current": str(current[f["field"]] or ""),
				"suggested": f["value"],
				# a detail the book already has is kept unless the person chooses the new one
				"decision": "Keep Current" if current[f["field"]] else "Use This",
				"image_no": f["leaf"] + 1,
				"found_text": f["snippet"],
				"how": f.get("how", "Rules"),
				"confidence": round(100 * f["confidence"]),
			}
			for f in found
		],
	)
	doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
	return {
		"status": doc.status,
		"entries": len(found),
		"message": _("{0} details found; they are a draft to check.").format(len(found)),
	}


def _from_assistant(pages: list[dict], current, have: set) -> list[dict]:
	"""What the rules missed, asked of the language model when the admin switched that on. Only values
	printed on the pages survive (core/llm.py)."""
	from sok_resdesk import assistant
	from sok_resdesk.core import llm

	missing = [f for f in rules.FIELDS if f not in have and not current[f]]
	if not missing or not assistant.enabled("titles"):
		return []
	front = pages[: rules.FRONT_PAGES][:4]  # the title page, its back and the next two
	system, user = llm.front_prompt(front, missing)
	found = llm.front_details(assistant.ask(system, user), front, current)
	return [{**f, "how": "Assistant"} for f in found if f["field"] in missing]


@frappe.whitelist(methods=["POST"])
def extract(item_id: str) -> dict:
	"""Read one book's title and imprint pages (staff)."""
	_staff_only()
	if not frappe.db.exists("RD Item", item_id):
		frappe.throw(_("No such book."), frappe.DoesNotExistError)
	return extract_now(item_id, frappe.session.user)


@frappe.whitelist(methods=["POST"])
def bulk(names=None, filters=None, everything: int = 0) -> dict:
	"""Read the details of many books in the background (managers and super admins). Books that already
	have a draft, or have no page text, are skipped; the results are drafts for librarians to check."""
	if not access.is_admin():
		frappe.throw(_("Only managers can run this over many books."), frappe.PermissionError)
	chosen = access.select_items(names, filters, None, None, None, None, bool(cint(everything)))
	todo = [n for n in chosen if not frappe.db.exists(DOCTYPE, n)]
	todo = [n for i in range(0, len(todo), 1000) for n in _with_text(todo[i : i + 1000])]
	if not todo:
		return {
			"count": 0,
			"message": _("Nothing to read: those books have no page text, or already have a draft."),
		}
	parts = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
	run = frappe.generate_hash(length=10)
	frappe.cache().set(_key(run, "left"), len(parts), ex=86400)
	frappe.cache.set_value(RUN + run, {"user": frappe.session.user, "total": len(todo)}, expires_in_sec=86400)
	for part in parts:
		frappe.enqueue(
			"sok_resdesk.frontmatter.extract_batch",
			queue="long",
			timeout=6 * 3600,
			names=part,
			run=run,
			user=frappe.session.user,
		)
	return {
		"count": len(todo),
		"message": _(
			"Reading details from {0} books in the background. You get an alert when it is done."
		).format(len(todo)),
	}


def _with_text(names: list[str]) -> list[str]:
	return frappe.get_all("RD Item", filters={"name": ("in", names), "has_page_text": 1}, pluck="name")


@hold_when_paused("long")
def extract_batch(names: list[str], run: str, user: str) -> None:
	counts = {"drafts": 0, "none": 0}
	for name in names:
		if frappe.cache.get_value("resdesk:stop-background"):
			break  # "Stop everything" on the Background Jobs page
		try:
			result = extract_now(name, user)
		except Exception:
			frappe.log_error(title=f"Research Desk: details of {name} could not be read")
			continue
		counts["drafts" if result["status"] == "Draft" else "none"] += 1
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

	subject = _("Details read from {0} books: {1} drafts to check, {2} with nothing new found.").format(
		state.get("total", 0), n("drafts"), n("none")
	)
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
		frappe.log_error(title="Research Desk: could not tell who ran the details job")


@frappe.whitelist(methods=["POST"])
def decide(item_id: str, status: str) -> dict:
	"""Apply the chosen details to the book (Applied) or throw the draft away (Rejected) (staff)."""
	_staff_only()
	if status not in ("Applied", "Rejected"):
		frappe.throw(_("Choose Applied or Rejected."))
	doc = frappe.get_doc(DOCTYPE, item_id)
	if doc.status != "Draft":
		frappe.throw(_("This draft was already decided."))
	if status == "Applied":
		_apply(doc)
	doc.status = status
	doc.reviewed_by = frappe.session.user
	doc.applied_on = now_datetime() if status == "Applied" else None
	doc.save(ignore_permissions=True)
	return {"status": doc.status}


def _apply(doc) -> None:
	"""Put the chosen details on the book. It is saved as a person's edit, so Keep My Edits switches on
	and a later ingest leaves the details alone; the book's usual push to other systems follows."""
	chosen = {
		r.field: (r.suggested or "").strip() for r in doc.details if r.decision == "Use This" and r.suggested
	}
	if not chosen:
		frappe.throw(_("No detail is set to Use This."))
	book = frappe.get_doc("RD Item", doc.item)
	for field, value in chosen.items():
		book.set(field, cint(value) if field == "year" else value)
	book.save(ignore_permissions=True)
