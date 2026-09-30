"""Keeping ingest profiles in step with archive.org (docs/ingesting.md#keeping-in-step-with-archiveorg).

After a profile's first completed run, each *sync run* asks archive.org only for what changed
since the last one ("In Step Up To" on the profile):

- books **added** to the collection or search since then come in (all of them);
- books **changed** since then are refreshed (Keep My Edits is respected);
- books **removed** from the collection, or made dark, are unpublished (and published again if
  they come back); if many seem to vanish at once, nothing is unpublished and managers are told;
- the profile's **portal collection** is filled and kept up to date.

Sync runs happen on the profile's schedule, or daily for profiles set to Manual.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime

OVERLAP_HOURS = 24  # archive.org's search index can lag behind: look back a day further
REMOVAL_GUARD = 0.1
CHECK_BY_NAME = 5000  # up to this many books, look them up by name instead of listing everything  # more than this share of a profile's books vanishing at once looks like a glitch


def is_sync_run(run, profile) -> bool:
	return bool(
		not profile.is_folder
		and cint(profile.keep_in_sync)
		and profile.synced_on
		and run.triggered_by in ("Scheduler", "Sync")
	)


def _stamp(dt) -> str:
	return get_datetime(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _since(profile) -> str:
	"""The last sync, in UTC for archive.org, a day earlier (its search index can lag)."""
	from datetime import UTC
	from zoneinfo import ZoneInfo

	from frappe.utils.data import get_system_timezone

	local = get_datetime(profile.synced_on).replace(tzinfo=ZoneInfo(get_system_timezone()))
	return _stamp(add_to_date(local.astimezone(UTC).replace(tzinfo=None), hours=-OVERLAP_HOURS))


def plan(run_name: str, profile, ia, log) -> list[str]:
	"""What a sync run should process: new books and changed ones. Also unpublishes removed
	books and republishes returning ones (those are processed again, to restore their pages)."""
	query = profile.build_query()
	since = _since(profile)
	log(f"Keeping in step with archive.org: changes since {since}")
	new = list(dict.fromkeys(ia.iter_identifiers(f"({query}) AND addeddate:[{since} TO null]")))
	existing = _existing(new)
	new = [i for i in new if i not in existing]
	log(f"{len(new):,} books added on archive.org since then")
	changed: list[str] = []
	if cint(profile.sync_changes):
		touched = list(dict.fromkeys(ia.iter_identifiers(f"({query}) AND oai_updatedate:[{since} TO null]")))
		mine = _existing(touched)
		changed = [i for i in touched if i in mine and i not in new]
		log(f"{len(changed):,} books in the catalogue changed on archive.org")
	back: list[str] = []
	if cint(profile.sync_removals) and profile.scope_type in ("Collection", "Search Query"):
		back = removals(run_name, profile, ia, query, log)
	return list(dict.fromkeys(new + changed + back))


def _existing(ids: list[str]) -> set[str]:
	out: set[str] = set()
	for i in range(0, len(ids), 1000):
		out.update(frappe.get_all("RD Item", filters={"name": ("in", ids[i : i + 1000])}, pluck="name"))
	return out


def removals(run_name: str, profile, ia, query: str, log) -> list[str]:
	"""Unpublish this profile's books that left archive.org; return the ones that came back."""
	rows = frappe.get_all(
		"RD Item",
		filters={"ingest_profile": profile.name, "source": ("!=", "Local")},
		fields=["name", "published", "removed_from_source"],
	)
	if not rows:
		return []
	if len(rows) <= CHECK_BY_NAME:
		# ask about this profile's own books, 50 at a time, rather than list a big collection
		on_ia: set[str] = set()
		names = [r.name for r in rows]
		for i in range(0, len(names), 50):
			chunk = " OR ".join(names[i : i + 50])
			on_ia.update(ia.iter_identifiers(f"({query}) AND identifier:({chunk})"))
	else:
		on_ia = set(ia.iter_identifiers(query))
	gone = [r.name for r in rows if r.name not in on_ia and r.published and not r.removed_from_source]
	back = [r.name for r in rows if r.name in on_ia and r.removed_from_source]
	if back:
		frappe.db.sql(
			"update `tabRD Item` set published=1, removed_from_source=0 where name in %s", (tuple(back),)
		)
		frappe.db.commit()
		log(f"{len(back):,} books are back on archive.org: published again")
	if not gone:
		return back
	if len(gone) > max(20, REMOVAL_GUARD * len(rows)):
		log(
			f"WARNING {len(gone):,} of {len(rows):,} books seem to have left archive.org at once; that "
			"looks like a problem on archive.org's side, so nothing was unpublished"
		)
		_alert(profile, len(gone), len(rows))
		return back
	removed = []
	collection = (profile.ia_collection or "").strip().lower()
	for item in gone:
		try:
			meta = ia.metadata(item).get("metadata", {})
		except Exception:
			meta = None  # dark or deleted
		if meta is not None:
			cols = meta.get("collection") or []
			cols = [cols] if isinstance(cols, str) else cols
			# still there (the search index lags), or a search profile: only dark books go
			if profile.scope_type != "Collection" or collection in {c.lower() for c in cols}:
				continue
		doc = frappe.get_doc("RD Item", item)
		doc.published = 0
		doc.removed_from_source = 1
		doc.save(ignore_permissions=True)  # also takes it out of the search index
		removed.append(item)
	frappe.db.commit()
	if removed:
		log(
			f"{len(removed):,} books left archive.org: unpublished ({', '.join(removed[:10])}{' …' if len(removed) > 10 else ''})"
		)
	return back


def _alert(profile, gone: int, total: int) -> None:
	try:
		from sok_resdesk.server import send_alert

		send_alert(
			"sync_guard",
			"bad",
			_(
				"Ingest profile {0}: {1} of {2} books seem to have left archive.org at once, so nothing was unpublished. Check the collection on archive.org."
			).format(profile.name, gone, total),
			link=f"/app/rd-ingest-profile/{profile.name}",
		)
	except Exception:
		frappe.log_error(title="Research Desk: could not send the sync alert")


def after_run(run_name: str) -> None:
	"""A run finished: remember how far the catalogue is in step, and update the portal collection."""
	run = frappe.db.get_value(
		"RD Ingest Run", run_name, ["profile", "status", "started_on", "creation"], as_dict=True
	)
	if not run or run.status not in ("Completed", "Completed with Errors"):
		return
	profile = frappe.get_doc("RD Ingest Profile", run.profile)
	if profile.is_folder:
		return
	started = run.started_on or run.creation
	if cint(profile.keep_in_sync) and (
		not profile.synced_on or get_datetime(started) > get_datetime(profile.synced_on)
	):
		frappe.db.set_value("RD Ingest Profile", profile.name, "synced_on", started, update_modified=False)
	if (
		cint(profile.mirror_collection)
		and profile.scope_type == "Collection"
		and (profile.ia_collection or "").strip()
	):
		name = ensure_mirror(profile)
		if name:
			sync_mirror(name)
	frappe.db.commit()


def ensure_mirror(profile) -> str | None:
	"""The portal collection for a profile's archive.org collection, made on first use."""
	ia_collection = profile.ia_collection.strip()
	name = profile.portal_collection
	if name and frappe.db.exists("RD Collection", name):
		return name
	name = frappe.db.get_value("RD Collection", {"mirror_of": ia_collection})
	if not name:
		title, description = ia_collection, ""
		try:
			from sok_resdesk.ingest import client

			meta = client().metadata(ia_collection).get("metadata", {})
			title = meta.get("title") or title
			title = title[0] if isinstance(title, list) else title
			description = meta.get("description") or ""
			description = "<br>".join(description) if isinstance(description, list) else description
		except Exception:
			pass  # named after the identifier; staff can rename it
		slug = frappe.scrub(ia_collection).replace("_", "-")
		if frappe.db.exists("RD Collection", slug):
			slug = f"{slug}-ia"
		doc = frappe.get_doc(
			{
				"doctype": "RD Collection",
				"title": title,
				"slug": slug,
				"published": 1,
				"description": description,
				"mirror_of": ia_collection,
				"rules": [{"match_on": "Source Collection", "how": "is exactly", "value": ia_collection}],
			}
		).insert(ignore_permissions=True)
		name = doc.name
	frappe.db.set_value("RD Ingest Profile", profile.name, "portal_collection", name, update_modified=False)
	return name


def sync_mirror(collection: str) -> tuple[int, int]:
	"""Make a mirror collection hold exactly the books in its archive.org collection."""
	from sok_resdesk import curation

	want = set(curation.rule_members(collection))
	gone = set(frappe.get_all("RD Item", filters={"removed_from_source": 1}, pluck="name"))
	want -= gone
	have = set(
		frappe.db.sql_list(
			"select parent from `tabRD Item Collection` where collection=%s and parenttype='RD Item'",
			collection,
		)
	)
	added = curation.add_items(collection, sorted(want - have))
	removed = curation.remove_items(collection, sorted(have - want))
	return added, removed


def run_daily() -> None:
	"""Daily (scheduler): sync profiles that are set to Manual but kept in step with archive.org.
	Profiles with a schedule sync on their schedule."""
	if cint(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest")):
		return
	from sok_resdesk.ingest import create_run, enqueue_plan

	for name in frappe.get_all(
		"RD Ingest Profile",
		filters={
			"enabled": 1,
			"schedule": "Manual",
			"keep_in_sync": 1,
			"source": "Internet Archive",
			"synced_on": ("is", "set"),
		},
		pluck="name",
	):
		if frappe.db.exists(
			"RD Ingest Run", {"profile": name, "status": ("in", ["Queued", "Running", "Paused"])}
		):
			continue
		run = create_run(frappe.get_doc("RD Ingest Profile", name), "Sync")
		enqueue_plan(run.name)


@frappe.whitelist()
def sync_now(profile: str) -> str:
	"""Sync one profile now (the profile form's Sync with archive.org button)."""
	from sok_resdesk.ingest import create_run, enqueue_plan

	doc = frappe.get_doc("RD Ingest Profile", profile)
	doc.check_permission("write")
	if not doc.synced_on:
		frappe.throw(_("Run this profile once first; after that, syncing brings in only what changed."))
	run = create_run(doc, "Sync")
	enqueue_plan(run.name)
	return run.name
