"""Helpers shared by the portal pages."""

from __future__ import annotations

import frappe

from sok_resdesk import access


def collection_cards() -> list[frappe._dict]:
	"""Published collections with the number of books this visitor can find in each."""
	rows = frappe.get_all(
		"RD Collection",
		filters={"published": 1},
		fields=[
			"name",
			"title",
			"cover_image",
			"featured",
			"sort_order",
			"curator",
			"description",
			"part_of",
		],
		order_by="sort_order asc, title asc",
	)
	if not rows:
		return []
	counts = dict(
		frappe.db.sql(
			f"""select c.collection, count(distinct i.name) from `tabRD Item Collection` c
		join `tabRD Item` i on i.name = c.parent
		where i.published = 1 and {access.sql_condition("i.visibility")} group by c.collection"""
		)
	)
	published = {r.name for r in rows}
	subs: dict[str, int] = {}
	for r in rows:
		r.count = counts.get(r.name, 0)
		if r.part_of and r.part_of not in published:
			r.part_of = None  # its parent isn't on the portal: show it at the top level
		if r.part_of:
			subs[r.part_of] = subs.get(r.part_of, 0) + 1
	for r in rows:
		r.subcollections = subs.get(r.name, 0)
	return rows


def facet_labels() -> dict:
	"""Display names for facet values that are ids (curated collections)."""
	return {"curated": dict(frappe.get_all("RD Collection", fields=["name", "title"], as_list=True))}
