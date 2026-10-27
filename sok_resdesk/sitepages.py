"""Pages of the organisation's own on the portal (/p/<address>), written in the Desk (RD Site Page)."""

from __future__ import annotations

import frappe

PREFIX = "/p/"


def route(slug: str) -> str:
	from urllib.parse import quote

	return PREFIX + quote(slug, safe="")


def get(slug: str) -> frappe._dict | None:
	"""The page at this address, or None. Unpublished pages are for staff only."""
	from sok_resdesk import access

	row = frappe.db.get_value(
		"RD Site Page",
		slug,
		["name", "title", "slug", "published", "members_only", "summary", "body"],
		as_dict=True,
	)
	if not row or not (row.published or access.is_staff()):
		return None
	return row


def sync_top_bar(doc) -> None:
	"""The page's link in the portal's top bar: after the Library and About links; gone when not wanted."""
	url = route(doc.slug)
	ws = frappe.get_single("Website Settings")
	items = list(ws.top_bar_items)
	mine = [i for i in items if (i.url or "") == url]
	want = bool(doc.published and doc.in_menu and not doc.members_only)
	label = (doc.menu_label or doc.title or "").strip()
	changed = False
	if want and mine:
		changed = mine[0].label != label
		mine[0].label = label
	elif want:
		ws.append("top_bar_items", {"label": label, "url": url})
		changed = True
	elif mine:
		for i in mine:
			ws.top_bar_items.remove(i)
		changed = True
	if changed:
		for n, i in enumerate(ws.top_bar_items, 1):
			i.idx = n
		ws.flags.ignore_permissions = True
		ws.save()
