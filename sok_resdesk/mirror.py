"""The public mirror: a second, read-only Research Desk on another container or server, fed only by
the main system (docs/governance.md#the-public-mirror).

This is the mirror's side. The main system's push target (outbound.py, "Public mirror") calls
`receive` with a book's catalogue record and files, or with `withdraw` when the book may no longer
be public. The mirror never connects to the main system, so the main system can stay on an internal
network and only needs a route out to this one.

Turned on in the site configuration (`resdesk_mirror`, with `resdesk_mirror_token`), not in the
Desk: nothing a Desk user does changes who may write here. The book is written as an IA-style folder
under the mirror's private files and read by the ordinary folder ingest, so searching, the reader,
IIIF and OAI-PMH on the mirror work as on any library.
"""

from __future__ import annotations

import hmac
import os
import re
import shutil

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from sok_resdesk.core.folder import META_SUFFIX, StoreError, parse_meta_xml

PROFILE = "Public mirror"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,98}$")
MAX_META = 1_000_000
MIN_TOKEN = 32  # a guessable token is no token
FILES = {"pdf": "{id}.pdf", "thumb": "__ia_thumb.jpg"}  # what the main system sends, and where it goes


def on() -> bool:
	return bool(frappe.conf.get("resdesk_mirror"))


def root() -> str:
	return frappe.get_site_path("private", "mirror")


def _auth() -> None:
	token = frappe.conf.get("resdesk_mirror_token") or ""
	sent = frappe.get_request_header("X-ResDesk-Mirror-Token") or ""
	if not on() or len(token) < MIN_TOKEN or not hmac.compare_digest(sent.encode(), token.encode()):
		frappe.throw(_("Not allowed."), frappe.PermissionError)
	frappe.set_user("Administrator")  # a checked machine call, acting as the system


def _folder(item: str) -> str:
	if not ID.match(item or ""):
		frappe.throw(_("Not a book identifier."))
	return os.path.join(root(), item)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=60, seconds=60)
def ping() -> str:
	"""For the main system's Test Connection: says this site's name when the token is right."""
	_auth()
	return frappe.local.site


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def receive(item: str | None = None, meta_xml: str | None = None, withdraw=0) -> dict:
	_auth()
	folder = _folder(item)
	if cint(withdraw):
		return _withdraw(item, folder)
	meta = (meta_xml or "").encode()
	if not meta or len(meta) > MAX_META:
		frappe.throw(_("The book's record is missing or too large."))
	try:
		parse_meta_xml(meta)
	except StoreError:
		frappe.throw(_("The book's record is not valid."))
	os.makedirs(folder, exist_ok=True)
	with open(os.path.join(folder, item + META_SUFFIX), "wb") as f:
		f.write(meta)
	for field, name in FILES.items():
		upload = (frappe.request.files or {}).get(field)
		if upload:  # whole file or nothing: a cut connection leaves no half book to be read
			target = os.path.join(folder, name.format(id=item))
			upload.save(target + ".part")
			os.replace(target + ".part", target)
	frappe.enqueue(
		"sok_resdesk.mirror.ingest_one",
		queue="long",
		timeout=3600,
		item=item,
		enqueue_after_commit=True,
		job_id=f"resdesk-mirror-{item}",
		deduplicate=True,
	)
	return {"received": item}


def _profile() -> str:
	from sok_resdesk.ingest import ensure_profile

	if frappe.db.exists("RD Ingest Profile", PROFILE):
		return PROFILE
	return ensure_profile(
		PROFILE,
		source="Folder or Server",
		location=root(),
		visibility="Public",
		check_archive_org=0,
		max_items=0,
		fetch_fulltext=1,
		schedule="Manual",
		notes="The public mirror's books, written by the main system (docs/governance.md).",
	)


def ingest_one(item: str) -> None:
	"""Background: read the folder the main system wrote, with the ordinary folder ingest."""
	from sok_resdesk.local_source import folder_store, ingest_local_one

	store = folder_store(root())
	profile = frappe.get_doc("RD Ingest Profile", _profile())
	ingest_local_one(store, item, item, profile, fetch_text=True, force=True)
	frappe.db.commit()


def _withdraw(item: str, folder: str) -> dict:
	"""The book may no longer be public: gone from the portal, the search engine and the disk."""
	from sok_resdesk.ingest import _cache_path
	from sok_resdesk.search import remove_record

	remove_record(item)  # raises if the search engine cannot be reached: the main system tries again
	try:
		os.remove(_cache_path(item))
	except FileNotFoundError:
		pass
	if frappe.db.exists("RD Item", item):
		frappe.delete_doc("RD Item", item, force=True, ignore_permissions=True)
	shutil.rmtree(folder, ignore_errors=True)
	frappe.db.commit()
	return {"withdrawn": item}
