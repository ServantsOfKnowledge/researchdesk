"""Manuscripts and palm-leaf bundles: labelling their leaves.

What is special about a manuscript is held on the book itself (the *Manuscript* section of an RD
Item: material, script, leaves, colophon…) and in its leaf labels. The leaves are transcribed in the
reader's Proofread mode like any page (from nothing: a manuscript needs no OCR text to start), by
people, and every version is kept. See docs/manuscripts.md.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import features
from sok_resdesk.core import leaves as core

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")


def _pages(item: str) -> int:
	total = cint(frappe.db.get_value("RD Item", item, "page_count"))
	if total <= 0:
		frappe.throw(_("The number of images is not known for this book: set Pages first."))
	return total


@frappe.whitelist()
@features.needs("manuscripts")
def label_leaves(
	item: str,
	sides: str = "a/b",
	start_image: int = 1,
	leaves: int = 0,
	start_folio: int = 1,
	preview: int = 0,
) -> dict:
	"""Give every image of the book its leaf label (1a, 1b, 2a…), or with preview=1 only show them."""
	frappe.only_for(STAFF)
	total = _pages(item)
	labels = core.labels(total, cint(start_image) or 1, cint(leaves), sides, cint(start_folio) or 1)
	shown = [{"image": i + 1, "label": labels[i]} for i in sorted(labels)[:14]]
	if cint(preview):
		return {"images": total, "labels": shown}
	frappe.db.set_value(
		"RD Item",
		item,
		"leaf_labels",
		json.dumps({str(i): v for i, v in labels.items()}),
		update_modified=False,
	)
	# what search finds and the reader shows follow the new labels
	frappe.enqueue(
		"sok_resdesk.search.reindex_item",
		queue="long",
		item_id=item,
		enqueue_after_commit=True,
		job_id=f"resdesk-relabel-{item}",
	)
	return {"images": total, "labels": shown, "saved": True}


@frappe.whitelist()
@features.needs("manuscripts")
def clear_labels(item: str) -> None:
	"""Back to the numbers the source gave."""
	frappe.only_for(STAFF)
	frappe.db.set_value("RD Item", item, "leaf_labels", "", update_modified=False)
	frappe.enqueue(
		"sok_resdesk.search.reindex_item",
		queue="long",
		item_id=item,
		enqueue_after_commit=True,
		job_id=f"resdesk-relabel-{item}",
	)
