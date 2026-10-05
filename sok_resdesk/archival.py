"""Archival description (Desk → Archival Description; the portal's /library/archive).

An archive's papers are described as a hierarchy of units (fonds, series, file, item: ISAD(G),
see core/archival.py), digitised items hang on the unit they belong to, and a fonds or collection
can be taken out as an EAD3 finding aid. A unit shows on the portal only when it and everything
above it are published, and visible to the reader as books are (public, or for logged-in readers).
"""

from __future__ import annotations

import frappe

from sok_resdesk import access, features
from sok_resdesk.catalogue import portal_title
from sok_resdesk.core import archival

DT = "RD Archival Unit"
FIELDS = [
	"name",
	"parent_unit as parent",
	"ref_code as ref",
	"title",
	"level",
	"date_text",
	"year_from",
	"year_to",
	"extent",
	"creator",
	"language",
	"physical",
	"admin_history",
	"custodial_history",
	"scope_content",
	"arrangement",
	"access_conditions",
	"reproduction_conditions",
	"finding_aids",
	"related_materials",
	"notes",
	"sort_order as sort",
	"published",
	"visibility",
]


def _all() -> list[dict]:
	return frappe.get_all(DT, fields=FIELDS, limit_page_length=0)


def shown(units: list[dict]) -> dict[str, dict]:
	"""{name: unit} of the units the current reader may see: published, findable by them, and with
	every ancestor so too (a hidden series hides what is under it)."""
	by = {u["name"]: u for u in units}
	ok: dict[str, bool] = {}

	def visible(name: str, seen=()) -> bool:
		if name in ok:
			return ok[name]
		u = by.get(name)
		if not u or name in seen:
			return False
		here = bool(u["published"]) and access.can_find(u["visibility"])
		ok[name] = here and (not u["parent"] or visible(u["parent"], (*seen, name)))
		return ok[name]

	return {n: u for n, u in by.items() if visible(n)}


def _staff() -> bool:
	return bool(set(frappe.get_roles()) & {"System Manager", "ResDesk Manager", "ResDesk Cataloguer"})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def ead(unit: str) -> None:
	"""A fonds or collection (and everything under it the reader may see) as an EAD3 finding aid."""
	if not features.on("archival"):
		raise frappe.PageDoesNotExistError
	units = _all()
	pool = shown(units) if not _staff() else {u["name"]: u for u in units}
	if unit not in pool:
		raise frappe.PageDoesNotExistError
	xml = archival.ead3(
		unit,
		[u for u in units if u["name"] in pool],
		portal_title(),
		frappe.utils.nowdate(),
	)
	frappe.local.response.filename = f"{pool[unit]['ref']}.xml"
	frappe.local.response.filecontent = xml.encode()
	frappe.local.response.type = "download"


def breadcrumbs(units: dict[str, dict], name: str) -> list[dict]:
	return archival.ancestors(units, name)


def unit_page(name: str) -> dict | None:
	"""Everything the portal's page of one unit needs, or None when the reader may not see it."""
	if not features.on("archival"):
		return None
	pool = shown(_all()) if not _staff() else {u["name"]: u for u in _all()}
	unit = pool.get(name)
	if not unit:
		return None
	kids = archival.children_of(list(pool.values())).get(name, [])
	items = frappe.get_all(
		"RD Item",
		filters={"archival_unit": name, "published": 1},
		fields=["name", "title", "visibility", "item_type", "year", "creator_display"],
		order_by="title asc",
	)
	return {
		"unit": unit,
		"trail": breadcrumbs(pool, name),
		"children": [k for k in kids if k["published"] or _staff()],
		"items": [i for i in items if access.can_find(i.visibility)],
		"ead": unit["level"] in ("Fonds", "Sub-fonds", "Collection"),
		"count": _count(pool, name),
	}


def _count(pool: dict[str, dict], name: str) -> int:
	"""Units described under this one, at any depth."""
	kids = archival.children_of(list(pool.values()))
	stack, n = list(kids.get(name, [])), 0
	while stack:
		u = stack.pop()
		n += 1
		stack += kids.get(u["name"], [])
	return n


def top_units() -> list[dict]:
	"""The fonds and collections a reader may see, for /library/archive."""
	if not features.on("archival"):
		return []
	pool = shown(_all()) if not _staff() else {u["name"]: u for u in _all()}
	return [
		{**u, "parts": _count(pool, u["name"])} for u in archival.children_of(list(pool.values())).get("", [])
	]


def item_trail(item_id: str) -> list[dict]:
	"""Where a digitised item sits in the archive's description (the unit and those above it, as
	far as the reader may see them), or [] for an item that is not described."""
	if not features.on("archival"):
		return []
	name = frappe.db.get_value("RD Item", item_id, "archival_unit")
	if not name:
		return []
	pool = shown(_all()) if not _staff() else {u["name"]: u for u in _all()}
	if name not in pool:
		return []
	return [*breadcrumbs(pool, name), pool[name]]
