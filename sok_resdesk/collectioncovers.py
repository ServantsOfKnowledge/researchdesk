"""Collection covers from archive.org (Desk → Collections; Get Image from archive.org).

A collection that mirrors an archive.org collection gets that collection's own picture (the logo
its curators uploaded, or the one archive.org shows), saved here so the portal never depends on
archive.org to show it. It fills in when the collection is made and whenever it has no cover. An
image a librarian uploads is theirs: it is never overwritten (we only replace the file we put
there ourselves). Unticking *Use archive.org's Image* stops it altogether.
"""

from __future__ import annotations

import frappe
from frappe import _

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")


def ours(doc) -> bool:
	"""Whether the cover is empty or still the one we took from archive.org (so we may replace it)."""
	return not doc.cover_image or doc.cover_image == doc.source_cover


def readable(data: bytes) -> bool:
	import io

	from PIL import Image

	try:
		with Image.open(io.BytesIO(data)) as im:
			im.load()
		return True
	except Exception:
		return False


def fetch(collection: str, identifier: str | None = None, force: bool = False) -> dict:
	"""Take the collection's image from archive.org. Without force, only when its cover is ours
	to change and archive.org's image is wanted. Returns {"ok", "message"}."""
	from sok_resdesk.ingest import client

	doc = frappe.get_doc("RD Collection", collection)
	identifier = (identifier or doc.image_from or doc.mirror_of or "").strip()
	if not identifier:
		return {"ok": False, "message": _("This collection has no archive.org identifier.")}
	if not force and (not doc.image_source or not ours(doc)):
		return {"ok": False, "message": _("Kept the cover it has.")}
	got = client().collection_image(identifier)
	if not got:
		return {"ok": False, "message": _("archive.org has no image for {0}.").format(identifier)}
	data, ext = got
	if not readable(data):
		return {
			"ok": False,
			"message": _("The image archive.org sent for {0} is damaged.").format(identifier),
		}
	old = doc.source_cover
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}-cover.{ext}",
			"content": data,
			"is_private": 0,
			"attached_to_doctype": "RD Collection",
			"attached_to_name": doc.name,
			"attached_to_field": "cover_image",
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		"RD Collection",
		doc.name,
		{"cover_image": f.file_url, "source_cover": f.file_url, "image_from": identifier, "image_source": 1},
		update_modified=False,
	)
	if old and old != f.file_url:
		for name in frappe.get_all(
			"File", filters={"file_url": old, "attached_to_name": doc.name}, pluck="name"
		):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)
	return {"ok": True, "message": _("The image from {0} is now its cover.").format(identifier)}


def fill_missing(names: list[str] | None = None) -> int:
	"""Covers for the collections that have none and an archive.org identifier (after a refresh
	of the mirrors, and from the Collections list). A collection that fails is tried next time."""
	filters = {"image_source": 1, "cover_image": ("is", "not set")}
	if names:
		filters["name"] = ("in", names)
	done = 0
	for row in frappe.get_all("RD Collection", filters=filters, fields=["name", "mirror_of", "image_from"]):
		if not (row.mirror_of or row.image_from):
			continue
		try:
			done += fetch(row.name)["ok"]
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Research Desk: no cover from archive.org for {row.name}")
	return done


# -- whitelisted -------------------------------------------------------------------------------


@frappe.whitelist()
def get_image(collection: str, identifier: str | None = None) -> dict:
	"""The form's button: take (or take again) the image now, replacing the cover."""
	frappe.only_for(STAFF)
	frappe.get_doc("RD Collection", collection).check_permission("write")
	return fetch(collection, identifier, force=True)


@frappe.whitelist()
def get_missing() -> dict:
	"""The Collections list's action: every collection without a cover, in the background."""
	frappe.only_for(STAFF)
	frappe.enqueue("sok_resdesk.collectioncovers.fill_missing", queue="long", timeout=3600)
	return {"queued": True}
