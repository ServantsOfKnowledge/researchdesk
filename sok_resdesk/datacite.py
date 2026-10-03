"""DOIs from DataCite for the books of chosen collections (Settings → DOIs, a collection's Give DOIs).

Each night (and from a collection's form) the books that should have a DOI and don't, or whose
metadata changed since it was sent, are registered or updated at DataCite (core/datacite.py
builds the record). A DOI points at the book's permanent link on the portal (its ARK when it has
one). On DataCite's test system DOIs are made the same way but never resolve, so they are kept
as *Test* and never put in citations. A book that is deleted keeps its DOI, which then leads to
the page saying what happened to the book.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.password import get_decrypted_password

from sok_resdesk.core import datacite as core

MANAGERS = ("System Manager", "ResDesk Manager")


def on() -> bool:
	return bool(cint(frappe.db.get_single_value("RD Settings", "doi_enabled")))


def _settings() -> dict:
	s = frappe.db.get_singles_dict("RD Settings")
	return {
		"test": bool(cint(s.get("datacite_test") if s.get("datacite_test") is not None else 1)),
		"prefix": (s.get("doi_prefix") or "").strip(),
		"shoulder": (s.get("doi_shoulder") or "").strip(),
		"repository": (s.get("datacite_repository") or "").strip(),
	}


def validate_settings(doc) -> None:
	"""RD Settings.validate: DOIs need a prefix and an account."""
	if not cint(doc.get("doi_enabled")):
		return
	try:
		core.check_prefix(doc.get("doi_prefix"))
	except core.DataCiteError as e:
		frappe.throw(str(e))
	if not (doc.get("datacite_repository") or "").strip():
		frappe.throw(_("Give the DataCite repository ID and password to give DOIs."))
	if doc.get("doi_shoulder") and core.SUFFIX_SAFE.search(doc.doi_shoulder.lower()):
		frappe.throw(_("A DOI shoulder uses only letters, digits, dots, dashes and underscores."))


def _session():
	import requests

	s = _settings()
	password = get_decrypted_password(
		"RD Settings", "RD Settings", "datacite_password", raise_exception=False
	)
	if not (s["repository"] and password):
		raise core.DataCiteError("Set the DataCite repository ID and password in Settings → DOIs.")
	session = requests.Session()
	session.auth = (s["repository"], password)
	session.headers.update(
		{
			"Content-Type": "application/vnd.api+json",
			"Accept": "application/vnd.api+json",
			"User-Agent": "SOK-ResearchDesk (+https://github.com/ServantsOfKnowledge/researchdesk)",
		}
	)
	return session, (core.TEST if s["test"] else core.PRODUCTION), s


def _record_and_url(name: str) -> tuple[dict, str]:
	from sok_resdesk.catalogue import base_url, item_to_record
	from sok_resdesk.core.citations import url_for

	record = item_to_record(frappe.get_doc("RD Item", name))
	return record, url_for({k: v for k, v in record.items() if k != "page_url"}, base_url())


def register(name: str, session=None, force: bool = False) -> str:
	"""Register (or update) one book's DOI. Returns what happened: made, updated, unchanged."""
	from sok_resdesk.catalogue import portal_title

	if session is None:
		session = _session()
	http, api, s = session
	item = frappe.db.get_value("RD Item", name, ["name", "doi", "doi_hash", "doi_state"], as_dict=True)
	record, url = _record_and_url(name)
	attrs = core.attributes(record, url, portal_title(), now_datetime().year)
	fingerprint = core.fingerprint(attrs)
	if item.doi and item.doi_hash == fingerprint and item.doi_state != "Failed" and not force:
		return "unchanged"
	doi = item.doi or core.doi_for(s["prefix"], name, s["shoulder"])
	body = core.payload(doi, attrs, "publish")
	resp = http.put(f"{api}/dois/{doi}", json=body, timeout=30)
	if resp.status_code == 404:  # not at DataCite yet: create it
		resp = http.post(f"{api}/dois", json=body, timeout=30)
	if resp.status_code not in (200, 201):
		try:
			problem = core.error_text(resp.json())
		except ValueError:
			problem = resp.text[:300]
		frappe.db.set_value(
			"RD Item", name, {"doi": item.doi or "", "doi_state": "Failed"}, update_modified=False
		)
		raise core.DataCiteError(f"DataCite said {resp.status_code}: {problem}")
	frappe.db.set_value(
		"RD Item",
		name,
		{
			"doi": doi,
			"doi_state": "Test" if s["test"] else "Findable",
			"doi_hash": fingerprint,
			"doi_on": now_datetime(),
		},
		update_modified=False,
	)
	return "updated" if item.doi else "made"


def wanted(limit: int = 1000) -> list[str]:
	"""Books that should have a DOI: published, public, in a collection that gives DOIs."""
	return frappe.db.sql_list(
		"""select distinct i.name from `tabRD Item` i
		join `tabRD Item Collection` c on c.parent = i.name and c.parenttype = 'RD Item'
		join `tabRD Collection` k on k.name = c.collection and k.give_dois = 1
		where i.published = 1 and ifnull(i.visibility, 'Public') = 'Public'
		order by (ifnull(i.doi, '') = '') desc, i.modified desc limit %s""",
		limit,
	)


def run(names: list[str] | None = None, limit: int = 1000) -> dict:
	"""Register or update DOIs for these books (default: every book that wants one)."""
	counts = {"made": 0, "updated": 0, "unchanged": 0, "failed": 0}
	if not on():
		return counts
	session = _session()
	for name in names if names is not None else wanted(limit):
		try:
			counts[register(name, session)] += 1
		except Exception as e:
			counts["failed"] += 1
			frappe.log_error(title=f"Research Desk: DOI for {name} failed", message=str(e)[:2000])
		frappe.db.commit()
	return counts


def daily() -> None:
	if on():
		run()


@frappe.whitelist(methods=["POST"])
def register_collection(collection: str) -> dict:
	"""Collection form → Register DOIs: its public books, in the background."""
	frappe.only_for(MANAGERS)
	if not on():
		frappe.throw(_("Switch DOIs on in Settings → DOIs first."))
	if not cint(frappe.db.get_value("RD Collection", collection, "give_dois")):
		frappe.throw(_("Tick Give DOIs on this collection first."))
	names = [n for n in wanted(100_000) if n in set(_collection_books(collection))]
	frappe.enqueue("sok_resdesk.datacite.run", queue="long", timeout=6 * 3600, names=names)
	return {"books": len(names)}


def _collection_books(collection: str) -> list[str]:
	return frappe.get_all(
		"RD Item Collection", filters={"collection": collection, "parenttype": "RD Item"}, pluck="parent"
	)


@frappe.whitelist(methods=["POST"])
def register_book(name: str) -> dict:
	"""Book form → Send to DataCite: register or update this book's DOI now."""
	frappe.only_for(MANAGERS)
	if not on():
		frappe.throw(_("Switch DOIs on in Settings → DOIs first."))
	if name not in wanted(100_000):
		frappe.throw(_("This book is not public in a collection that gives DOIs."))
	try:
		return {"result": register(name, force=True), "doi": frappe.db.get_value("RD Item", name, "doi")}
	except core.DataCiteError as e:
		frappe.throw(str(e))


def on_item_trash(doc) -> None:
	"""A deleted book keeps its DOI: it is pointed at the book's tombstone page."""
	if not doc.get("doi") or doc.get("doi_state") != "Findable" or not on():
		return
	frappe.enqueue(
		"sok_resdesk.datacite.point_at_tombstone",
		queue="long",
		doi=doc.doi,
		ark=doc.get("persistent_id") or f"doi:{doc.doi}",
		enqueue_after_commit=True,
	)


def point_at_tombstone(doi: str, ark: str) -> None:
	from urllib.parse import quote

	from sok_resdesk.catalogue import base_url

	http, api, _s = _session()
	url = f"{base_url()}/library/withdrawn?ark={quote(ark, safe='')}"
	body = {"data": {"id": doi, "type": "dois", "attributes": {"url": url}}}
	resp = http.put(f"{api}/dois/{doi}", json=body, timeout=30)
	if resp.status_code != 200:
		frappe.log_error(
			title=f"Research Desk: DOI {doi} not pointed at its tombstone", message=resp.text[:2000]
		)


def health_check() -> dict:
	"""For the Server page: DOIs off, or how many are registered and failed."""
	if not on():
		return {
			"key": "dois",
			"label": _("DOIs"),
			"state": "off",
			"detail": _("off"),
			"link": "/app/rd-settings",
		}
	failed = frappe.db.count("RD Item", {"doi_state": "Failed"})
	made = frappe.db.count("RD Item", {"doi_state": ("in", ("Findable", "Test"))})
	test = " (" + _("test system") + ")" if _settings()["test"] else ""
	return {
		"key": "dois",
		"label": _("DOIs"),
		"state": "warn" if failed else "ok",
		"detail": _("{0} registered, {1} failed").format(made, failed) + test,
		"link": "/app/rd-item?doi_state=Failed" if failed else "/app/rd-settings",
	}
