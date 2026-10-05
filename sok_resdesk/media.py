"""Audio and video: what staff do to a recording beyond ingesting it.

A recording is catalogued from a folder (its media files, an optional WebVTT or SRT transcript,
a poster and a `<name>.json` of details) or from archive.org. Its transcript is kept as segments:
pages of text with start and end seconds, so search, proofreading and citations work on them.
Without a transcript, *Lay out segments* makes blank ones for people to transcribe.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import features
from sok_resdesk.core import media as core

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")


def _recording(item: str):
	frappe.only_for(STAFF)
	doc = frappe.get_doc("RD Item", item)
	if not doc.media_files:
		frappe.throw(_("This book is not a recording."))
	return doc


@frappe.whitelist(methods=["POST"])
@features.needs("media")
def read_length(item: str) -> dict:
	"""Read the recording's length from its file (a folder's recording)."""
	doc = _recording(item)
	if doc.source != "Local":
		frappe.throw(_("The length of an archive.org recording is read from archive.org."))
	from sok_resdesk.local_source import store_for_item

	store = store_for_item(doc)
	loc = doc.local_path
	secs = 0
	for name in store.media_files(loc) if store else []:
		path = store.file_path(loc, name)
		secs = max(secs, int(round(core.duration_of(path))) if path else 0)
	if not secs:
		frappe.throw(_("The length could not be read: install ffprobe, or the mutagen library."))
	doc.db_set("duration", secs)
	return {"duration": secs}


@frappe.whitelist(methods=["POST"])
@features.needs("media")
def lay_out_segments(item: str, seconds: int = 60) -> dict:
	"""Blank transcript segments over the whole recording, for people to fill in. Not over a
	transcript that exists."""
	doc = _recording(item)
	if doc.leaf_times:
		frappe.throw(_("This recording already has transcript segments."))
	if not cint(doc.duration):
		frappe.throw(_("The recording's length is not known yet: read it first."))
	segs = core.blank_segments(cint(doc.duration), cint(seconds) or 60)
	doc.db_set({"leaf_times": core.times_json(segs), "page_count": len(segs)})
	frappe.get_doc("RD Item", item)  # (the record is read fresh by the page)
	return {"segments": len(segs)}
