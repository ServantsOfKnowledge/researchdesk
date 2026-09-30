"""Curated collections: membership, rules, bulk changes and keeping the search index in step."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.core import collections as core
from sok_resdesk.holding import hold_when_paused

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")
BACKGROUND_OVER = 200
CHILD = "tabRD Item Collection"


# -- reading ----------------------------------------------------------------------------------


def of_item(item: str) -> list[str]:
	return frappe.db.sql_list(
		f"select collection from `{CHILD}` where parent=%s and parenttype='RD Item' order by idx", item
	)


def titles(names: list[str] | None = None) -> dict[str, str]:
	filters = {"name": ("in", names)} if names else {}
	return dict(frappe.get_all("RD Collection", filters=filters, fields=["name", "title"], as_list=True))


def refresh_counts(names: list[str] | None = None) -> None:
	for name in names or frappe.get_all("RD Collection", pluck="name"):
		count = frappe.db.sql(
			f"select count(distinct parent) from `{CHILD}` where collection=%s and parenttype='RD Item'", name
		)[0][0]
		frappe.db.set_value("RD Collection", name, "item_count", count, update_modified=False)


# -- changing membership --------------------------------------------------------------------------


@hold_when_paused("long")
def add_items(collection: str, names: list[str], reindex: bool = True) -> int:
	"""Add books to a collection (skips books already in it). Returns how many were added."""
	names = list(dict.fromkeys(n for n in names if n))
	if not names:
		return 0
	added = []
	for i in range(0, len(names), 500):
		chunk = names[i : i + 500]
		have = set(
			frappe.db.sql_list(
				f"select parent from `{CHILD}` where collection=%s and parenttype='RD Item' and parent in %s",
				(collection, tuple(chunk)),
			)
		)
		existing_items = set(
			frappe.db.sql_list("select name from `tabRD Item` where name in %s", (tuple(chunk),))
		)
		for item in chunk:
			if item in have or item not in existing_items:
				continue
			idx = frappe.db.sql(f"select ifnull(max(idx),0)+1 from `{CHILD}` where parent=%s", item)[0][0]
			frappe.db.sql(
				f"""insert into `{CHILD}` (name, creation, modified, owner, modified_by, docstatus, idx,
				parent, parenttype, parentfield, collection) values (%s, now(), now(), %s, %s, 0, %s, %s,
				'RD Item', 'curated_collections', %s)""",
				(
					frappe.generate_hash(length=12),
					frappe.session.user,
					frappe.session.user,
					idx,
					item,
					collection,
				),
			)
			added.append(item)
		frappe.db.commit()
	_touch(added)
	refresh_counts([collection])
	frappe.db.commit()
	if reindex:
		update_index(added)
	return len(added)


@hold_when_paused("long")
def remove_items(collection: str, names: list[str], reindex: bool = True) -> int:
	names = list(dict.fromkeys(n for n in names if n))
	removed = []
	for i in range(0, len(names), 500):
		chunk = tuple(names[i : i + 500])
		removed += frappe.db.sql_list(
			f"select parent from `{CHILD}` where collection=%s and parenttype='RD Item' and parent in %s",
			(collection, chunk),
		)
		frappe.db.sql(
			f"delete from `{CHILD}` where collection=%s and parenttype='RD Item' and parent in %s",
			(collection, chunk),
		)
		frappe.db.commit()
	_touch(removed)
	refresh_counts([collection])
	frappe.db.commit()
	if reindex:
		update_index(removed)
	return len(removed)


def _touch(names: list[str]) -> None:
	"""Bump `modified` so OAI-PMH harvesters pick up the change."""
	for i in range(0, len(names), 500):
		frappe.db.sql("update `tabRD Item` set modified=now() where name in %s", (tuple(names[i : i + 500]),))


def update_index(names: list[str]) -> None:
	"""Refresh collection membership (and other catalogue fields) in both search indexes."""
	from sok_resdesk.search import update_item_fields

	if names:
		# small changes made from a page wait for the index, so a reload shows them
		update_item_fields(names, wait=len(names) <= BACKGROUND_OVER and not frappe.flags.in_background_job)


# -- rules --------------------------------------------------------------------------------------


def _rules(collection: str) -> list[dict]:
	return frappe.db.sql(
		"select match_on, how, value from `tabRD Collection Rule` where parent=%s and parenttype='RD Collection' order by idx",
		collection,
		as_dict=True,
	)


def rule_members(collection: str) -> list[str]:
	"""Every book in the catalogue that matches the collection's rules."""
	from sok_resdesk.access import _rule_records

	rules = _rules(collection)
	if not rules:
		return []
	records = _rule_records()
	types = dict(frappe.db.sql("select name, ifnull(item_type,'Book') from `tabRD Item`"))
	return [
		name for name, rec in records.items() if core.matches({**rec, "item_type": types.get(name)}, rules)
	]


@hold_when_paused("long")
def apply_rules_now(collection: str) -> int:
	added = add_items(collection, rule_members(collection))
	frappe.db.set_value(
		"RD Collection", collection, "rules_applied_on", now_datetime(), update_modified=False
	)
	frappe.db.commit()
	return added


def collections_for_new_item(record: dict, profile: str | None) -> list[str]:
	"""Collections whose rules match a newly ingested book."""
	rows = frappe.db.sql(
		"""select r.parent, r.match_on, r.how, r.value from `tabRD Collection Rule` r
		join `tabRD Collection` c on c.name = r.parent where r.parenttype='RD Collection'""",
		as_dict=True,
	)
	by_collection: dict[str, list[dict]] = {}
	for r in rows:
		by_collection.setdefault(r.parent, []).append(r)
	rec = {**record, "ingest_profile": profile or ""}
	return [c for c, rules in by_collection.items() if core.matches(rec, rules)]


# -- whitelisted actions ----------------------------------------------------------------------------


@frappe.whitelist()
def bulk(
	action: str,
	collection: str,
	names=None,
	filters=None,
	profile=None,
	language=None,
	search=None,
	source_collection=None,
	everything: int = 0,
) -> dict:
	"""Add books to, or remove them from, a collection. Choose books like bulk_set_visibility."""
	frappe.only_for(STAFF)
	if action not in ("add", "remove"):
		frappe.throw(_("Action must be add or remove"))
	if not frappe.db.exists("RD Collection", collection):
		frappe.throw(_("No collection called {0}").format(collection))
	from sok_resdesk.access import select_items

	selected = select_items(
		names, filters, source_collection, profile, language, search, bool(cint(everything))
	)
	if not selected:
		return {"count": 0, "message": _("No books matched.")}
	fn = "sok_resdesk.curation.add_items" if action == "add" else "sok_resdesk.curation.remove_items"
	title = frappe.db.get_value("RD Collection", collection, "title")
	if len(selected) > BACKGROUND_OVER:
		frappe.enqueue(fn, queue="long", timeout=6 * 3600, collection=collection, names=selected)
		return {
			"count": len(selected),
			"queued": True,
			"message": _("Updating {0} books in “{1}” in the background.").format(len(selected), title),
		}
	n = frappe.get_attr(fn)(collection, selected)
	verb = _("added to") if action == "add" else _("removed from")
	return {"count": n, "message": _("{0} books {1} “{2}”.").format(n, verb, title)}


@frappe.whitelist()
def apply_rules(collection: str) -> dict:
	frappe.only_for(STAFF)
	members = rule_members(collection)
	if len(members) > BACKGROUND_OVER:
		frappe.enqueue(
			"sok_resdesk.curation.apply_rules_now", queue="long", timeout=6 * 3600, collection=collection
		)
		return {"message": _("Checking {0} matching books in the background.").format(len(members))}
	n = apply_rules_now(collection)
	return {"message": _("{0} books added ({1} matched the rules).").format(n, len(members))}


@frappe.whitelist()
def create(title: str, description: str = "") -> str:
	"""Quick-create a collection (used from the list/portal 'add to collection' dialogs)."""
	frappe.only_for(STAFF)
	doc = frappe.get_doc({"doctype": "RD Collection", "title": title, "description": description}).insert()
	return doc.name


def on_collection_trash(doc, method=None):
	names = frappe.db.sql_list(f"select parent from `{CHILD}` where collection=%s", doc.name)
	frappe.db.sql(f"delete from `{CHILD}` where collection=%s", doc.name)
	update_index(names)
