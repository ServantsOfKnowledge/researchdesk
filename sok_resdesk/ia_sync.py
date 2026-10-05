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
		profile.on_archive_org
		# a file, or a fixed list of books, has no new books to find on archive.org
		and profile.get("scope_type") not in ("Metadata File", "Identifier List")
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
			"update `tabRD Item` set published=1, removed_from_source=0, served_from_copy=0 where name in %s",
			(tuple(back),),
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
	from sok_resdesk import preservation

	removed, kept = [], []
	keep_from_copy = bool(frappe.db.get_single_value("RD Settings", "serve_from_copy"))
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
		doc.removed_from_source = 1
		if keep_from_copy and preservation.copy_pdf(doc.item_id):
			# Settings → Keep Dropped Books on the Portal: its PDF now comes from our copy
			doc.served_from_copy = 1
			kept.append(item)
		else:
			doc.published = 0
			removed.append(item)
		doc.save(ignore_permissions=True)  # also updates (or takes it out of) the search index
		if doc.served_from_copy:
			preservation.event(item, "Access from copy", "Success", "archive.org no longer serves it")
	frappe.db.commit()
	if removed:
		log(
			f"{len(removed):,} books left archive.org: unpublished ({', '.join(removed[:10])}{' …' if len(removed) > 10 else ''})"
		)
	if kept:
		log(
			f"{len(kept):,} books left archive.org: kept on the portal from our copy ({', '.join(kept[:10])}{' …' if len(kept) > 10 else ''})"
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
	"""A run finished: remember how far the catalogue is in step, and update the portal collections."""
	run = frappe.db.get_value(
		"RD Ingest Run", run_name, ["profile", "status", "started_on", "creation"], as_dict=True
	)
	if not run or run.status not in ("Completed", "Completed with Errors"):
		return
	profile = frappe.get_doc("RD Ingest Profile", run.profile)
	if not profile.on_archive_org:
		return
	started = run.started_on or run.creation
	if cint(profile.keep_in_sync) and (
		not profile.synced_on or get_datetime(started) > get_datetime(profile.synced_on)
	):
		frappe.db.set_value("RD Ingest Profile", profile.name, "synced_on", started, update_modified=False)
	frappe.db.commit()
	refresh_mirrors()


# -- portal collections that mirror archive.org ------------------------------------------------------

# archive.org's own groupings that say nothing about the books' subject or source
NOT_COLLECTIONS = {
	"additional_collections",
	"americana",
	"books_by_language",
	"community",
	"folkscanomy",
	"inlibrary",
	"internetarchivebooks",
	"opensource",
	"printdisabled",
	"texts",
}


def _members() -> tuple[dict[str, set[str]], dict[str, str]]:
	"""archive.org collection (lower case) -> books in it, and the identifier as archive.org spells it."""
	members: dict[str, set[str]] = {}
	spelling: dict[str, str] = {}
	for name, cols in frappe.db.sql(
		"""select name, collections from `tabRD Item`
		where ifnull(source, '') not in ('Local', 'Repository') and ifnull(removed_from_source, 0) = 0"""
	):
		for c in (cols or "").splitlines():
			c = c.strip()
			if c:
				members.setdefault(c.lower(), set()).add(name)
				spelling.setdefault(c.lower(), c)
	return members, spelling


def wanted_collections(members: dict[str, set[str]], spelling: dict[str, str]) -> list[str]:
	"""Which archive.org collections get a portal page: every one the books are in (Settings), and
	the collection of each profile that asks for one."""
	s = frappe.db.get_singles_dict("RD Settings")
	want: dict[str, str] = {}
	mirror_all = s.get("mirror_all_collections")
	if mirror_all in (None, "") or cint(mirror_all):
		skip = {
			x.strip().lower()
			for x in (s.get("mirror_skip") or "").replace(",", "\n").splitlines()
			if x.strip()
		}
		smallest = max(1, cint(s.get("mirror_min_books")) or 1)
		for key, books in members.items():
			if key in skip or key in NOT_COLLECTIONS or key.startswith("fav-") or len(books) < smallest:
				continue
			want[key] = spelling[key]
	for p in frappe.get_all(
		"RD Ingest Profile",
		filters={"source": "Internet Archive", "scope_type": "Collection", "mirror_collection": 1},
		fields=["name", "ia_collection"],
	):
		key = (p.ia_collection or "").strip().lower()
		if key and key in members:
			want.setdefault(key, spelling.get(key) or p.ia_collection.strip())
	return sorted(want.values(), key=str.lower)


def refresh_mirrors(profile: str | None = None) -> dict:
	"""Make and fill the portal collections that mirror archive.org: after every run, after an
	upgrade, and when the settings change. Returns counts for the log."""
	members, spelling = _members()
	made = added = removed = 0
	for ia_id in wanted_collections(members, spelling):
		try:
			name, _parent, new = ensure_mirror(ia_id)
			made += new
			a, r = sync_mirror(name, members.get(ia_id.lower(), set()))
			added, removed = added + a, removed + r
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Research Desk: could not update the portal collection for {ia_id}")
	# collections made before their archive.org parent was recorded: look it up once
	for name, ia_id in frappe.get_all(
		"RD Collection",
		filters={"mirror_of": ("is", "set"), "mirror_parent": ("is", "not set")},
		fields=["name", "mirror_of"],
		as_list=True,
	):
		if frappe.db.get_value("RD Collection", name, "mirror_parent") is None:
			frappe.db.set_value(
				"RD Collection", name, "mirror_parent", _ia_parent(ia_id), update_modified=False
			)
	frappe.db.commit()
	# sub-collections: shown under the collection they belong to on archive.org, when it has a page
	by_ia = dict(
		frappe.get_all(
			"RD Collection", filters={"mirror_of": ("is", "set")}, fields=["mirror_of", "name"], as_list=True
		)
	)
	by_ia = {k.lower(): v for k, v in by_ia.items()}
	for name, parent in frappe.get_all(
		"RD Collection",
		filters={"mirror_parent": ("is", "set")},
		fields=["name", "mirror_parent"],
		as_list=True,
	):
		target = by_ia.get(parent.lower())
		if target and target != name and not frappe.db.get_value("RD Collection", name, "part_of"):
			frappe.db.set_value("RD Collection", name, "part_of", target, update_modified=False)
	for p in frappe.get_all(
		"RD Ingest Profile",
		filters={
			"source": "Internet Archive",
			"scope_type": "Collection",
			**({"name": profile} if profile else {}),
		},
		fields=["name", "ia_collection", "portal_collection"],
	):
		target = by_ia.get((p.ia_collection or "").strip().lower())
		if target and p.portal_collection != target:
			frappe.db.set_value(
				"RD Ingest Profile", p.name, "portal_collection", target, update_modified=False
			)
	frappe.db.commit()
	return {"made": made, "added": added, "removed": removed}


def on_profile_update(doc, method=None) -> None:
	"""Portal collection switched on (or the collection changed): make it now, in the background."""
	if (
		doc.source == "Internet Archive"
		and doc.scope_type == "Collection"
		and cint(doc.mirror_collection)
		and (doc.has_value_changed("mirror_collection") or doc.has_value_changed("ia_collection"))
	):
		frappe.enqueue("sok_resdesk.ia_sync.refresh_mirrors", queue="long", enqueue_after_commit=True)


def on_settings_update(doc, method=None) -> None:
	if any(doc.has_value_changed(f) for f in ("mirror_all_collections", "mirror_min_books", "mirror_skip")):
		frappe.enqueue("sok_resdesk.ia_sync.refresh_mirrors", queue="long", enqueue_after_commit=True)


def _ia_parent(ia_collection: str) -> str:
	try:
		from sok_resdesk.ingest import client

		parent = client().metadata(ia_collection).get("metadata", {}).get("collection") or ""
	except Exception:
		return ""
	parents = [parent] if isinstance(parent, str) else parent
	return next((c for c in parents if c and c.lower() not in NOT_COLLECTIONS), "")


def ensure_mirror(ia_collection: str) -> tuple[str, str, bool]:
	"""The portal collection for an archive.org collection, made on first use with its name and
	description from archive.org. Returns (name, the archive.org collection it is part of, made now)."""
	name = frappe.db.get_value("RD Collection", {"mirror_of": ia_collection})
	if name:
		return name, "", False
	title, description, parent = ia_collection, "", ""
	try:
		from sok_resdesk.ingest import client

		meta = client().metadata(ia_collection).get("metadata", {})
		title = meta.get("title") or title
		title = title[0] if isinstance(title, list) else title
		description = meta.get("description") or ""
		description = "<br>".join(description) if isinstance(description, list) else description
		parent = meta.get("collection") or ""
		parent = next(
			(
				c
				for c in ([parent] if isinstance(parent, str) else parent)
				if c.lower() not in NOT_COLLECTIONS
			),
			"",
		)
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
			"mirror_parent": parent,
			"rules": [{"match_on": "Source Collection", "how": "is exactly", "value": ia_collection}],
		}
	).insert(ignore_permissions=True)
	return doc.name, parent, True


def sync_mirror(collection: str, want: set[str] | None = None) -> tuple[int, int]:
	"""Make a mirror collection hold exactly the books in its archive.org collection."""
	from sok_resdesk import curation

	if want is None:
		ia_id = frappe.db.get_value("RD Collection", collection, "mirror_of") or ""
		want = _members()[0].get(ia_id.lower(), set())
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
