"""Books from Wikisource: an Ingest Profile whose source is *Wikisource*.

The profile names a Wikisource (kn.wikisource.org…) and a category of Index pages and/or a list
of them. Each Index page is a book: its details become the catalogue record, and the text of
its pages (``core/wikisource.py``) becomes the book's page text, taken page by page at the
proofreading level the profile asks for (any text, proofread, or validated). The scan stays on
Wikisource (Wikimedia Commons): page images are drawn there, and the book page links to the
Index and to the scan. The text is CC BY-SA 4.0, and the record says so.

Books are fetched again on every run (the wiki's pages are read in bulk, and an unchanged book
is left as it is); *Refresh Items Already in Catalogue* forces them all.
"""

from __future__ import annotations

import hashlib

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import features
from sok_resdesk.catalogue import item_to_record, upsert_item
from sok_resdesk.core import wikisource as ws
from sok_resdesk.core.normalize import normalize_ia_item

SOURCE = "Wikisource"


def client(profile) -> ws.WikiClient:
	return ws.WikiClient(profile.wiki_site or "")


def _title(raw: str) -> str:
	"""`Name.pdf` or `Index:Name.pdf` (or the wiki's own word for Index) → `Index:Name.pdf`."""
	raw = raw.strip()
	return raw if ":" in raw else f"Index:{raw}"


def index_titles(profile, limit: int = 0) -> list[str]:
	"""The Index pages the profile names: its list, then its category's, once each."""
	out = [_title(t) for t in (profile.wiki_indexes or "").splitlines() if t.strip()]
	category = (profile.wiki_category or "").strip()
	if category:
		wiki = client(profile)
		index_ns, _page_ns = wiki.namespaces()
		for title in wiki.indexes_in_category(category, index_ns):
			out.append(title)
			if limit and len(out) >= limit:
				break
	return list(dict.fromkeys(out))[: limit or None]


@frappe.whitelist()
@features.needs("repositories")
def check(profile: str) -> dict:
	"""Ingest Profile → Check Wikisource: how many Index pages, and a sample book's details."""
	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("read")
	try:
		titles = index_titles(doc)
		sample = None
		if titles:
			wiki = client(doc)
			fields = ws.parse_index(wiki.wikitext(titles[0]))
			sample = {
				"index": titles[0],
				"item_id": ws.item_id_for(doc.wiki_site, titles[0]),
				"title": fields.get("title") or ws.filename_of(titles[0]),
				"author": fields.get("author", ""),
				"year": fields.get("year", ""),
				"pages": wiki.file_pages(ws.filename_of(titles[0])),
			}
	except ws.WikiError as e:
		frappe.throw(_("The Wikisource did not answer as expected: {0}").format(str(e)[:300]))
	return {"books": len(titles), "sample": sample}


def plan(run_name: str, profile, limit: int, log) -> list[list]:
	"""The books to do: [[item_id, Index title], …] for the batches."""
	log(
		f"Listing the Index pages of {profile.wiki_site}"
		+ (f" in {profile.wiki_category}" if profile.wiki_category else "")
	)
	titles = index_titles(profile, limit)
	log(f"{len(titles):,} books to catalogue")
	return [[ws.item_id_for(profile.wiki_site, t), t] for t in titles]


def pages_of(wiki: ws.WikiClient, index_title: str, level: int) -> tuple[list[dict], bool, int]:
	"""(page texts at or above `level`, whether they are all proofread, scan pages seen)."""
	filename = ws.filename_of(index_title)
	_index_ns, page_ns = wiki.namespaces()
	pages, seen, checked = [], 0, True
	for p in wiki.pages(filename, page_ns):
		seen = max(seen, p["leaf"] + 1)
		if p["quality"] < level or not p["text"].strip():
			continue
		pages.append({"leaf": p["leaf"], "text": p["text"], "label": str(p["leaf"] + 1)})
		checked = checked and p["quality"] >= 3
	return pages, checked and bool(pages), seen


def ingest_one(entry: list, profile, fetch_text: bool, force: bool = False, buffer=None) -> tuple[str, int]:
	"""Catalogue one book (and its page text). Returns (outcome, pages indexed)."""
	from sok_resdesk.ingest import PAGE_ORDER, cache_enabled, write_cached_pages
	from sok_resdesk.search import SearchError, index_record

	item_id, index_title = entry[0], entry[1]
	site = profile.wiki_site
	wiki = client(profile)
	filename = ws.filename_of(index_title)
	try:
		wikitext = wiki.wikitext(index_title)
		scan_pages = wiki.file_pages(filename)
		level = ws.MIN_LEVEL.get(profile.wiki_quality or "Proofread", 3)
		pages, proofread, seen = pages_of(wiki, index_title, level) if fetch_text else ([], False, 0)
	except ws.WikiError as e:
		raise RuntimeError(str(e)) from e
	digest = hashlib.sha1(  # noqa: S324 (a change detector, not a secret)
		(wikitext + "|" + "|".join(f"{p['leaf']}:{p['text']}" for p in pages)).encode()
	).hexdigest()[:20]
	signature = f"{digest}|{level}|{int(bool(fetch_text))}"
	existing = frappe.db.get_value("RD Item", item_id, ["source_signature"], as_dict=True)
	if existing and not force and existing.source_signature == signature:
		return "unchanged", 0

	fields = ws.parse_index(wikitext)
	meta = ws.meta(
		fields, site=site, index_title=index_title, pages=scan_pages or seen, scan=ws.file_url(site, filename)
	)
	record = normalize_ia_item(item_id, meta, [])
	text_source = ("Wikisource (proofread)" if proofread else "Wikisource") if pages else ""
	record.update(
		{
			"source": SOURCE,
			"on_archive_org": False,
			"access_status": "Open",
			"source_url": ws.index_url(site, index_title),
			"thumbnail_url": ws.image_url(site, filename, 0, 300),
			"ark": "",
			"remote_pdf": ws.file_url(site, filename),
			"wiki_site": site,
			"wiki_index": index_title,
			"page_count": scan_pages or seen or record.get("page_count") or 0,
			"has_page_text": bool(pages),
			"has_fulltext": bool(pages),
			"text_source": text_source,
			"source_signature": signature,
		}
	)
	name, created = upsert_item(
		record, raw={"wikisource": {"index": index_title, "fields": fields}}, profile=profile.name
	)
	if pages and cache_enabled():
		write_cached_pages(item_id, pages)
	if pages:
		frappe.db.set_value("RD Item", name, "page_order", PAGE_ORDER, update_modified=False)
	try:
		from sok_resdesk.pagetext import apply

		record = item_to_record(frappe.get_doc("RD Item", name))
		pages = apply(item_id, pages)
		if buffer is not None:
			return ("created" if created else "updated"), buffer.add(
				record, pages, replace_pages=not created, if_changed=True
			)
		count = index_record(record, pages, replace_pages=not created)
	except SearchError as e:
		frappe.log_error("Research Desk: indexing failed", f"{item_id}: {e}")
		count = 0
	return ("created" if created else "updated"), count


def source_pages(item_id: str) -> list[dict]:
	"""A Wikisource book's page text when the local cache doesn't have it: read it again."""
	row = frappe.db.get_value("RD Item", item_id, ["wiki_site", "wiki_index", "ingest_profile"], as_dict=True)
	if not row or not row.wiki_site or not row.wiki_index:
		return []
	quality = (
		frappe.db.get_value("RD Ingest Profile", row.ingest_profile, "wiki_quality")
		if row.ingest_profile
		else ""
	)
	try:
		pages, _proofread, _seen = pages_of(
			ws.WikiClient(row.wiki_site), row.wiki_index, ws.MIN_LEVEL.get(quality or "Proofread", 3)
		)
	except ws.WikiError:
		return []
	return pages


def refresh(doc) -> None:
	"""Item → Refresh: read this one book again from its Wikisource."""
	if not doc.wiki_index or not doc.ingest_profile:
		frappe.throw(_("This book's Wikisource page is not known."))
	profile = frappe.get_doc("RD Ingest Profile", doc.ingest_profile)
	ingest_one([doc.name, doc.wiki_index], profile, fetch_text=True, force=True)


def page_image_url(record: dict, leaf: int, width: int = ws.PAGE_WIDTH) -> str:
	"""A page of a Wikisource book as an image (the wiki draws it from the scan)."""
	if not record.get("wiki_site") or not record.get("wiki_index"):
		return ""
	return ws.image_url(record["wiki_site"], ws.filename_of(record["wiki_index"]), cint(leaf), width)


# -- giving corrections back (0.50) -----------------------------------------------------------------------

SEND_LICENCES = ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0")  # text Wikisource can take (it is CC BY-SA 4.0)
SEND_MAX = 25  # pages in one go: each is a real edit on the wiki, so it goes slowly and in view
SEND_PAUSE = 1.5  # seconds between edits


def _page_title(index_title: str, leaf: int, page_ns: str = "Page") -> str:
	return f"{page_ns}:{ws.filename_of(index_title)}/{int(leaf) + 1}"


def _my_book(item: str):
	from sok_resdesk import wikimedia

	frappe.only_for(wikimedia.WORKERS)
	row = frappe.db.get_value("RD Item", item, ["wiki_site", "wiki_index", "item_id"], as_dict=True)
	if not row or not row.wiki_site or not row.wiki_index:
		frappe.throw(_("This book does not come from a Wikisource."))
	return row


def send_licence_problem() -> str:
	"""'' when the library's text licence lets its corrections go to Wikisource, else why not."""
	chosen = (frappe.db.get_single_value("RD Settings", "ground_truth_licence") or "").strip()
	if chosen in SEND_LICENCES:
		return ""
	return _(
		"Wikisource's text is CC BY-SA 4.0, so only text this library shares under CC0, CC-BY or "
		"CC-BY-SA can go back. Choose the licence in Settings (Ground truth licence) first."
	)


def _plan_pages(row, client, me: str) -> list[dict]:
	"""What this person could send for the book, checked against the pages as they are on the wiki now.
	Only the person's own work: a page they proofread (to *proofread*) or validated (to *validated*)."""
	from sok_resdesk import pagetext

	mine = {
		leaf: v
		for leaf, v in pagetext.current(row.item_id).items()
		if v.status in pagetext.HUMAN
		and frappe.db.get_value(pagetext.DT, v.name, ["proofread_by", "validated_by"])
	}
	if not mine:
		return []
	titles = {leaf: _page_title(row.wiki_index, leaf, "Page") for leaf in mine}
	live = ws.revisions(client, list(titles.values()))
	out = []
	for leaf in sorted(mine):
		v, title = mine[leaf], titles[leaf]
		entry = {"leaf": leaf, "page": title, "label": v.page_label or str(leaf + 1), "kind": "", "skip": ""}
		out.append(entry)
		who = frappe.db.get_value(pagetext.DT, v.name, ["proofread_by", "validated_by"], as_dict=True)
		i_proofread = who.proofread_by == frappe.session.user
		i_validated = v.status == "Validated" and who.validated_by == frappe.session.user
		if not (i_proofread or i_validated):
			entry["skip"] = _("Done by someone else: they can send it from their own account.")
			continue
		page = live.get(title)
		if not page:
			entry["skip"] = _("This page does not exist on Wikisource (pages are never created from here).")
			continue
		parts = ws.split_page(page["content"])
		if not parts:
			entry["skip"] = _("The page has an unusual layout, so it is left alone.")
			continue
		head, body, foot = parts
		wiki = ws.parse_page(page["content"])
		unchanged = ws.same_text(v.text, wiki["text"])
		entry.update({"revid": page["revid"], "from_level": wiki["quality"]})
		if wiki["quality"] >= 4:
			entry["skip"] = _("Already validated on Wikisource.")
		elif wiki["quality"] == 3:
			if not (i_validated and unchanged):
				entry["skip"] = _(
					"Already proofread on Wikisource; what is there is not overwritten from here."
				)
			elif wiki["user"] == me:
				entry["skip"] = _("You proofread this page there: another person has to validate it.")
			else:
				entry.update({"kind": "validated", "to_level": 4, "diff": []})
		elif not i_proofread:
			entry["skip"] = _("Validated here, but proofread by someone else: that person sends it first.")
		elif not unchanged and not ws.markup_safe(body):
			entry["skip"] = _(
				"The page has markup (templates, links, notes) that plain text would lose: correct it on Wikisource."
			)
		else:
			entry.update(
				{
					"kind": "proofread",
					"to_level": 3,
					"diff": ws.diff_lines(wiki["text"], v.text) if not unchanged else [],
				}
			)
	return out


@frappe.whitelist()
@features.needs("repositories")
def send_plan(item: str) -> dict:
	"""Item → Send to Wikisource: what this person's own corrections would change there."""
	from sok_resdesk import wikimedia
	from sok_resdesk.core import wikimedia as wm

	row = _my_book(item)
	acc = frappe.db.get_value(wikimedia.DOCTYPE, frappe.session.user, "wikimedia_user")
	out = {
		"site": row.wiki_site,
		"index": row.wiki_index,
		"account": acc or "",
		"problem": send_licence_problem() or ("" if acc else _("Connect your own Wikimedia account first.")),
		"pages": [],
		"max": SEND_MAX,
	}
	if out["problem"]:
		return out
	client = wm.WikimediaClient.for_site(row.wiki_site, wikimedia.need_account())
	try:
		out["pages"] = _plan_pages(row, client, acc)
	except wm.WikimediaError as e:
		frappe.throw(_("Wikisource did not answer as expected: {0}").format(str(e)[:300]))
	return out


@frappe.whitelist(methods=["POST"])
@features.needs("repositories")
def send_pages(item: str, pages) -> list[dict]:
	"""Send the reviewed pages: [{"leaf", "revid"}, …] (the revision each was reviewed against).
	A page changed on Wikisource since the review is not sent: the edit names the revision it is
	based on, so the wiki itself refuses it. Returns what happened to each."""
	import json
	import time

	from sok_resdesk import wikimedia
	from sok_resdesk.core import wikimedia as wm

	row = _my_book(item)
	if send_licence_problem():
		frappe.throw(send_licence_problem())
	asked = json.loads(pages) if isinstance(pages, str) else pages
	if not asked or len(asked) > SEND_MAX:
		frappe.throw(_("Choose between 1 and {0} pages to send at a time.").format(SEND_MAX))
	me = frappe.db.get_value(wikimedia.DOCTYPE, frappe.session.user, "wikimedia_user")
	client = wm.WikimediaClient.for_site(row.wiki_site, wikimedia.need_account())
	plan = {p["leaf"]: p for p in _plan_pages(row, client, me)}
	results = []
	for n, a in enumerate(asked):
		leaf = cint(a.get("leaf"))
		entry = plan.get(leaf)
		res = {"leaf": leaf, "page": entry["page"] if entry else "", "result": ""}
		results.append(res)
		if not entry or not entry.get("kind"):
			res["result"] = _("Skipped: ") + (entry["skip"] if entry else _("not one of your pages"))
			continue
		if cint(a.get("revid")) != cint(entry["revid"]):
			res["result"] = _("Skipped: it changed on Wikisource after you reviewed it. Review it again.")
			continue
		page = ws.revisions(client, [entry["page"]])[entry["page"]]
		head, body, foot = ws.split_page(page["content"])
		mine = frappe.db.get_value(
			"RD Page Text", {"item": row.item_id, "leaf": leaf, "is_current": 1}, "text"
		)
		# unchanged text keeps the page's own markup; a corrected one (checked as plain) replaces it
		text = body if ws.same_text(mine, ws.plain(body)) else mine
		new = ws.build_page(head, text, foot, entry["to_level"], me)
		if n:
			time.sleep(SEND_PAUSE)
		try:
			client.post(
				action="edit",
				title=entry["page"],
				text=new,
				baserevid=entry["revid"],
				nocreate=1,
				summary=("Validated" if entry["kind"] == "validated" else "Proofread")
				+ " with SOK Research Desk",
				token=client.csrf(),
			)
			res["result"] = "validated" if entry["kind"] == "validated" else "proofread"
		except wm.WikimediaError as e:
			res["result"] = (
				_("Not sent: it changed on Wikisource meanwhile.")
				if str(e).startswith("editconflict")
				else _("Not sent: {0}").format(str(e)[:200])
			)
	wikimedia.touch(frappe.session.user)
	sent = [r for r in results if r["result"] in ("proofread", "validated")]
	if sent:
		frappe.get_doc("RD Item", item).add_comment(
			"Info",
			_("{0} sent {1} page(s) to {2} as {3}.").format(
				frappe.session.user, len(sent), row.wiki_site, me
			),
		)
	return results
