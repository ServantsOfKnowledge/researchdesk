"""Integration tests for running a library: pushing metadata, pausing and resuming work, quiet hours,
the getting-started checklist and moving an install. They need a site but no network:

bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_operations

Much of this code commits as it goes (so a pause is seen by every worker at once), so these tests
clean up after themselves instead of relying on a rollback.
"""

import json
import os
import tempfile
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk.catalogue import upsert_item
from sok_resdesk.core.normalize import normalize_ia_item

PREFIX = "rdtest.ops"
SETTINGS_FIELDS = (
	"pause_background",
	"pause_scheduled_ingest",
	"held_jobs",
	"quiet_hours",
	"quiet_from",
	"quiet_to",
	"quiet_weekdays_only",
	"resource_preset",
	"book_limit",
	"mirror_all_collections",
	"mirror_min_books",
	"mirror_skip",
)
DEFAULTS = (
	"resdesk_schedules_were_paused",
	"resdesk_quiet_state",
	"resdesk_quiet_paused",
	"resdesk_checklist",
)


def _item(n: int) -> str:
	identifier = f"{PREFIX}{n:04d}"
	meta = {
		"identifier": identifier,
		"title": f"Operations test book {n}",
		"creator": ["Test Author"],
		"date": "1950",
		"language": "English",
		"collection": ["ServantsOfKnowledge"],
	}
	upsert_item(normalize_ia_item(identifier, meta, []), raw=meta)
	return identifier


class FakeHook:
	"""Stands in for the webhook client; can pause or cancel the run after a number of books."""

	def __init__(self, run_name=None, pause_after=None, status="Paused"):
		self.sent, self.run_name, self.pause_after, self.status = [], run_name, pause_after, status

	def send(self, event, payload):
		self.sent.append(payload.get("identifier") or payload.get("id"))
		if self.pause_after and len(self.sent) == self.pause_after:
			frappe.db.sql("update `tabRD Push Run` set status=%s where name=%s", (self.status, self.run_name))
		return 200


class OpsTestCase(IntegrationTestCase):
	def setUp(self):
		self._saved = {f: frappe.db.get_single_value("RD Settings", f) for f in SETTINGS_FIELDS}
		self._defaults = {k: frappe.db.get_default(k) for k in DEFAULTS}
		frappe.db.set_single_value("RD Settings", {"pause_background": 0, "held_jobs": ""})
		self.enqueued = []
		patcher = mock.patch(
			"frappe.enqueue", side_effect=lambda method, **kw: self.enqueued.append((method, kw))
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")
		for doctype, field in (
			("RD External Record", "item"),
			("RD Item Collection", "parent"),
			("RD Item", "name"),
		):
			frappe.db.delete(doctype, {field: ("like", f"{PREFIX}%")})
		for run in frappe.get_all("RD Push Run", filters={"target": ("like", "rdtest%")}, pluck="name"):
			frappe.db.delete("RD Push Run", run)
		frappe.db.delete("RD Push Target", {"name": ("like", "rdtest%")})
		frappe.db.delete("RD Collection Rule", {"parent": ("like", "rdtest%")})
		frappe.db.delete("RD Collection", {"name": ("like", "rdtest%")})
		frappe.db.delete("RD Ingest Run", {"profile": ("like", "rdtest%")})
		frappe.db.delete("RD Ingest Profile", {"name": ("like", "rdtest%")})
		frappe.db.set_single_value("RD Settings", {k: v for k, v in self._saved.items()})
		for k, v in self._defaults.items():
			frappe.db.set_default(k, v or "")
		frappe.db.commit()
		frappe.clear_document_cache("RD Settings", "RD Settings")


class TestPush(OpsTestCase):
	def _target(self, **extra):
		from sok_resdesk import curation

		coll = frappe.get_doc(
			{"doctype": "RD Collection", "title": "rdtest push", "slug": "rdtest-push"}
		).insert(ignore_permissions=True)
		self.books = [_item(n) for n in range(1, 6)]
		curation.add_items(coll.name, self.books, reindex=False)
		return frappe.get_doc(
			{
				"doctype": "RD Push Target",
				"target_name": "rdtest hook",
				"target_type": "Webhook",
				"hook_url": "http://receiver.invalid/hook",
				"scope": "Collection",
				"collection": coll.name,
				"dry_run": 0,
				**extra,
			}
		).insert(ignore_permissions=True)

	def test_push_sends_then_skips_unchanged(self):
		from sok_resdesk import outbound

		t = self._target()
		fake = FakeHook()
		with mock.patch.object(outbound, "_client", return_value=fake):
			run = outbound._start(t.name)
			self.assertEqual(self.enqueued[-1][0], "sok_resdesk.outbound.run")
			outbound.run(run)
			r = frappe.get_doc("RD Push Run", run)
			self.assertEqual((r.status, r.sent, r.failed), ("Completed", 5, 0))
			self.assertEqual(frappe.db.count("RD External Record", {"target": t.name}), 5)

			again = outbound._start(t.name)
			outbound.run(again)
			r = frappe.get_doc("RD Push Run", again)
			self.assertEqual((r.sent, r.unchanged), (0, 5))
		self.assertEqual(len(fake.sent), 5)

	def test_dry_run_sends_nothing(self):
		from sok_resdesk import outbound

		t = self._target(dry_run=1)
		fake = FakeHook()
		with mock.patch.object(outbound, "_client", return_value=fake):
			run = outbound._start(t.name)
			outbound.run(run)
		self.assertEqual(frappe.db.get_value("RD Push Run", run, "sent"), 5)
		self.assertEqual(fake.sent, [])
		self.assertFalse(frappe.db.count("RD External Record", {"target": t.name}))

	def test_pause_mid_run_then_resume(self):
		from sok_resdesk import jobs, outbound

		t = self._target()
		with mock.patch.object(outbound, "_client") as client:
			run = outbound._start(t.name)
			client.return_value = FakeHook(run, pause_after=2)
			outbound.run(run)
			r = frappe.get_doc("RD Push Run", run)
			held = json.loads(r.held_items)
			self.assertEqual(r.status, "Paused")
			self.assertEqual(len(held["items"]), 3)
			self.assertEqual(r.sent, 2)

			self.enqueued.clear()
			jobs.resume_run(run)
			method, kw = self.enqueued[-1]
			self.assertEqual((method, kw["resume"], len(kw["items"])), ("sok_resdesk.outbound.run", 1, 3))
			client.return_value = FakeHook()
			outbound.run(run, items=kw["items"], resume=1)
		r = frappe.get_doc("RD Push Run", run)
		self.assertEqual((r.status, r.sent, r.held_items), ("Completed", 5, None))

	def test_cancel_before_start_and_mid_run(self):
		from sok_resdesk import outbound

		t = self._target()
		fake = FakeHook()
		with mock.patch.object(outbound, "_client", return_value=fake):
			run = outbound._start(t.name)
			outbound.cancel(run)  # still waiting in the queue: it never starts
			outbound.run(run)
			self.assertEqual(frappe.db.get_value("RD Push Run", run, "status"), "Cancelled")
			self.assertEqual(fake.sent, [])

			run = outbound._start(t.name)
			fake.run_name, fake.pause_after, fake.status = run, 2, "Cancelled"
			outbound.run(run)
		r = frappe.get_doc("RD Push Run", run)
		self.assertEqual((r.status, r.sent), ("Cancelled", 2))
		self.assertEqual(len(fake.sent), 2)

	def test_pause_refused_when_not_running(self):
		from sok_resdesk import jobs, outbound

		t = self._target()
		with mock.patch.object(outbound, "_client", return_value=FakeHook()):
			run = outbound._start(t.name)
			outbound.run(run)
		self.assertRaises(frappe.ValidationError, jobs.pause_run, run)
		self.assertRaises(frappe.ValidationError, jobs.resume_run, run)


class TestPauseAll(OpsTestCase):
	def _ingest_run(self, status="Running") -> str:
		if not frappe.db.exists("RD Ingest Profile", "rdtest profile"):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": "rdtest profile",
					"source": "Internet Archive",
					"identifiers": "rdtest.none",
				}
			).insert(ignore_permissions=True)
		run = frappe.get_doc(
			{"doctype": "RD Ingest Run", "profile": "rdtest profile", "status": status}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return run.name

	def test_pause_all_and_resume_all(self):
		from sok_resdesk import holding, jobs

		frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 0)
		run = self._ingest_run()
		with mock.patch.object(jobs, "_rq_jobs", return_value=[]):
			jobs.pause_all()
			self.assertTrue(holding.is_paused())
			self.assertEqual(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest"), 1)
			self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "status"), "Paused")
			self.assertRaises(frappe.ValidationError, jobs.resume_run, run)  # Pause All wins
			jobs.resume_all()
		self.assertFalse(holding.is_paused())
		self.assertEqual(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest"), 0)
		self.assertNotEqual(frappe.db.get_value("RD Ingest Run", run, "status"), "Paused")

	def test_schedules_paused_before_stay_paused(self):
		from sok_resdesk import jobs

		frappe.db.set_single_value("RD Settings", "pause_scheduled_ingest", 1)
		with mock.patch.object(jobs, "_rq_jobs", return_value=[]):
			jobs._pause_all("test")
			jobs._resume_all("test")
		self.assertEqual(frappe.db.get_single_value("RD Settings", "pause_scheduled_ingest"), 1)

	def test_held_jobs_are_released_or_discarded(self):
		from sok_resdesk import holding

		a = holding.hold("sok_resdesk.search.rebuild_index", {"x": 1}, queue="long", kind="search")
		holding.hold("sok_resdesk.search.rebuild_index", {"x": 2}, queue="default")
		self.assertEqual(len(holding.held_jobs()), 2)
		self.assertEqual(holding.release([a], discard=True), 1)
		self.assertEqual(self.enqueued, [])
		self.assertEqual(holding.release(), 1)
		self.assertEqual(self.enqueued[-1][0], "sok_resdesk.search.rebuild_index")
		self.assertEqual(self.enqueued[-1][1]["x"], 2)
		self.assertEqual(holding.held_jobs(), [])


class TestQuietHours(OpsTestCase):
	def _window(self, inside: bool):
		from frappe.utils import add_to_date, now_datetime

		now = now_datetime()
		start = add_to_date(now, minutes=-30 if inside else 60)
		end = add_to_date(now, minutes=30 if inside else 120)
		frappe.db.set_single_value(
			"RD Settings",
			{
				"quiet_hours": 1,
				"quiet_from": start.strftime("%H:%M:00"),
				"quiet_to": end.strftime("%H:%M:00"),
				"quiet_weekdays_only": 0,
			},
		)
		frappe.db.commit()

	def test_quiet_hours_pause_and_resume(self):
		from sok_resdesk import holding, jobs

		frappe.db.set_default("resdesk_quiet_state", "outside")
		with mock.patch.object(jobs, "_rq_jobs", return_value=[]):
			self._window(inside=True)
			jobs.apply_quiet_hours()
			self.assertTrue(holding.is_paused())
			jobs.apply_quiet_hours()  # nothing changes while still inside
			self.assertTrue(holding.is_paused())
			self._window(inside=False)
			jobs.apply_quiet_hours()
		self.assertFalse(holding.is_paused())

	def test_manual_choices_are_respected(self):
		from sok_resdesk import holding, jobs

		frappe.db.set_default("resdesk_quiet_state", "outside")
		with mock.patch.object(jobs, "_rq_jobs", return_value=[]):
			self._window(inside=True)
			jobs.apply_quiet_hours()
			jobs.resume_all()  # a manager resumes by hand during quiet hours
			jobs.apply_quiet_hours()
			self.assertFalse(holding.is_paused())

			jobs._pause_all("manager")  # paused by hand outside quiet hours is never lifted
			frappe.db.set_default("resdesk_quiet_state", "outside")
			frappe.db.set_default("resdesk_quiet_paused", "")
			self._window(inside=True)
			jobs.apply_quiet_hours()
			self._window(inside=False)
			jobs.apply_quiet_hours()
		self.assertTrue(holding.is_paused())


class TestSetupHelpers(OpsTestCase):
	def test_checklist_steps(self):
		from sok_resdesk import guide

		guide.restart_checklist()
		state = guide.checklist()
		self.assertEqual(len(state["steps"]), len(guide.STEPS))
		self.assertFalse(state["hidden"])
		key = state["steps"][0]["key"]
		after = guide.checklist_mark(key, "skipped")
		self.assertTrue(after["steps"][0]["skipped"])
		guide.mark_visited("jobs")
		self.assertIn("jobs", guide._state()["done"])
		self.assertTrue(guide.checklist_mark("", "hide")["hidden"])
		self.assertRaises(frappe.ValidationError, guide.checklist_mark, "no-such-step")

	def test_choose_preset(self):
		from sok_resdesk import jobs

		jobs.choose_preset("light")
		self.assertEqual(frappe.db.get_single_value("RD Settings", "resource_preset"), "light")
		self.assertRaises(frappe.ValidationError, jobs.choose_preset, "huge")

	def test_portable_paths_and_relink(self):
		from sok_resdesk.local_source import DEFAULT_ROOT, portable_path, relink

		with tempfile.TemporaryDirectory() as lib:
			os.makedirs(os.path.join(lib, "shelf"))
			with mock.patch.dict(frappe.local.conf, {"resdesk_library_dir": lib}):
				self.assertEqual(portable_path(os.path.join(lib, "shelf")), f"{DEFAULT_ROOT}/shelf")
				self.assertEqual(portable_path("/elsewhere/x"), "/elsewhere/x")
				self.assertEqual(portable_path("https://example.org/x"), "https://example.org/x")

		book = _item(9)
		frappe.db.set_value("RD Item", book, "local_store", "/old/disk/shelf_1")
		frappe.db.set_value("RD Item", _item(10), "local_store", "/old/diskette/shelf")
		counts = relink("/old/disk")
		self.assertEqual(counts["RD Item"], 1)
		self.assertEqual(frappe.db.get_value("RD Item", book, "local_store"), f"{DEFAULT_ROOT}/shelf_1")
		self.assertEqual(
			frappe.db.get_value("RD Item", f"{PREFIX}0010", "local_store"), "/old/diskette/shelf"
		)


class FakeIA:
	"""archive.org for the sync tests: a collection whose books come, change and go."""

	def __init__(self):
		self.books = {f"{PREFIX}{n:04d}": f"Sync book {n}" for n in range(1, 5)}
		self.added: set[str] = set()
		self.changed: set[str] = set()
		self.dark: set[str] = set()
		self.moved: set[str] = set()  # still on archive.org, but in another collection
		self.sub: set[str] = set()  # also in the sub-collection rdtestsub

	def iter_identifiers(self, query, limit=0, page_size=1000):
		if "addeddate" in query:
			return iter(sorted(self.added))
		if "oai_updatedate" in query:
			return iter(sorted(self.changed | self.added))
		return iter(sorted(set(self.books) - self.dark - self.moved))

	def count(self, query):
		return len(list(self.iter_identifiers(query)))

	def metadata(self, identifier):
		from sok_resdesk.core.ia import IAError

		if identifier == "rdtestcoll":
			return {"metadata": {"title": "RD Test Collection", "description": "From archive.org"}}
		if identifier == "rdtestsub":
			return {"metadata": {"title": "RD Test Sub", "collection": ["printdisabled", "rdtestcoll"]}}
		if identifier in self.dark or identifier not in self.books:
			raise IAError("item not found or dark")
		coll = ["othercoll"] if identifier in self.moved else ["rdtestcoll"]
		if identifier in self.sub:
			coll.append("rdtestsub")
		meta = {
			"identifier": identifier,
			"title": self.books[identifier],
			"language": "English",
			"collection": coll,
		}
		return {"metadata": meta, "files": []}


class TestIASync(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"book_limit": "No limit", "mirror_all_collections": 0})
		self.ia = FakeIA()
		for p in (
			mock.patch("sok_resdesk.ingest.client", return_value=self.ia),
			mock.patch("sok_resdesk.search.index_record", return_value=0),
			mock.patch("sok_resdesk.search.update_item_fields"),
			mock.patch("sok_resdesk.search.remove_record"),
			mock.patch("sok_resdesk.search.MeiliClient.from_settings"),
		):
			p.start()
			self.addCleanup(p.stop)
		self.profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest sync",
				"source": "Internet Archive",
				"scope_type": "Collection",
				"ia_collection": "rdtestcoll",
				"max_items": 0,
				"fetch_fulltext": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

	def run_profile(self, triggered_by):
		from sok_resdesk.ingest import create_run, run_ingest

		run = create_run(frappe.get_doc("RD Ingest Profile", self.profile.name), triggered_by)
		frappe.db.commit()
		run_ingest(run.name, foreground=True)
		return frappe.get_doc("RD Ingest Run", run.name)

	def test_first_run_then_syncs(self):
		first = self.run_profile("Manual")
		self.assertEqual((first.status, first.created_count), ("Completed", 4), first.log)
		profile = frappe.get_doc("RD Ingest Profile", self.profile.name)
		self.assertTrue(profile.synced_on)
		# the portal collection mirrors the archive.org collection
		coll = profile.portal_collection
		self.assertEqual(
			frappe.db.get_value("RD Collection", coll, ["title", "mirror_of"]),
			("RD Test Collection", "rdtestcoll"),
		)
		self.assertEqual(frappe.db.count("RD Item Collection", {"collection": coll}), 4)

		# on archive.org: one book added, one changed, one made dark, one moved elsewhere
		self.ia.books[f"{PREFIX}0005"] = "Sync book 5"
		self.ia.added = {f"{PREFIX}0005"}
		self.ia.books[f"{PREFIX}0001"] = "Sync book 1, corrected"
		self.ia.changed = {f"{PREFIX}0001"}
		self.ia.dark = {f"{PREFIX}0002"}
		self.ia.moved = {f"{PREFIX}0003"}
		sync = self.run_profile("Sync")
		self.assertEqual(sync.status, "Completed")
		self.assertEqual((sync.created_count, sync.updated_count), (1, 1))
		self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}0001", "title"), "Sync book 1, corrected")
		for gone in ("0002", "0003"):
			self.assertEqual(
				frappe.db.get_value("RD Item", f"{PREFIX}{gone}", ["published", "removed_from_source"]),
				(0, 1),
			)
		self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}0004", "published"), 1)
		members = set(frappe.get_all("RD Item Collection", filters={"collection": coll}, pluck="parent"))
		self.assertEqual(members, {f"{PREFIX}0001", f"{PREFIX}0004", f"{PREFIX}0005"})

		# a book that comes back is published again
		self.ia.dark, self.ia.added, self.ia.changed = set(), set(), set()
		self.run_profile("Sync")
		self.assertEqual(
			frappe.db.get_value("RD Item", f"{PREFIX}0002", ["published", "removed_from_source"]), (1, 0)
		)
		self.assertIn(
			f"{PREFIX}0002",
			frappe.get_all("RD Item Collection", filters={"collection": coll}, pluck="parent"),
		)

	def test_mass_disappearance_unpublishes_nothing(self):
		from sok_resdesk import ia_sync

		self.run_profile("Manual")
		self.ia.books.update({f"{PREFIX}{n:04d}": f"Sync book {n}" for n in range(5, 30)})
		self.ia.added = {f"{PREFIX}{n:04d}" for n in range(5, 30)}
		self.run_profile("Sync")
		self.ia.added = set()
		self.ia.dark = set(list(self.ia.books)[:25])  # 25 of 29 vanish at once
		with mock.patch("sok_resdesk.server.send_alert") as alert:
			self.run_profile("Sync")
		self.assertEqual(frappe.db.count("RD Item", {"name": ("like", f"{PREFIX}%"), "published": 0}), 0)
		self.assertEqual(alert.call_args.args[0], "sync_guard")
		self.assertEqual(ia_sync.REMOVAL_GUARD, 0.1)

	def test_manual_runs_and_unsynced_profiles_are_full_runs(self):
		from sok_resdesk import ia_sync

		run = frappe._dict(triggered_by="Manual")
		profile = frappe.get_doc("RD Ingest Profile", self.profile.name)
		self.assertFalse(ia_sync.is_sync_run(run, profile))  # never run yet
		self.assertRaises(frappe.ValidationError, ia_sync.sync_now, profile.name)
		profile.synced_on = frappe.utils.now_datetime()
		self.assertTrue(ia_sync.is_sync_run(frappe._dict(triggered_by="Sync"), profile))
		self.assertFalse(ia_sync.is_sync_run(run, profile))
		profile.keep_in_sync = 0
		self.assertFalse(ia_sync.is_sync_run(frappe._dict(triggered_by="Scheduler"), profile))

	def test_portal_collection_made_after_upgrade_and_when_switched_on(self):
		from sok_resdesk import ia_sync

		frappe.db.set_value("RD Ingest Profile", self.profile.name, "mirror_collection", 0)
		self.run_profile("Manual")  # books in, but no portal collection asked for
		self.assertFalse(frappe.db.get_value("RD Ingest Profile", self.profile.name, "portal_collection"))
		profile = frappe.get_doc("RD Ingest Profile", self.profile.name)
		profile.mirror_collection = 1
		self.enqueued.clear()
		profile.save()
		self.assertEqual(self.enqueued[-1][0], "sok_resdesk.ia_sync.refresh_mirrors")
		ia_sync.refresh_mirrors(**{k: v for k, v in self.enqueued[-1][1].items() if k == "profile"})
		coll = frappe.db.get_value("RD Ingest Profile", self.profile.name, "portal_collection")
		self.assertEqual(frappe.db.get_value("RD Collection", coll, "mirror_of"), "rdtestcoll")
		self.assertEqual(frappe.db.count("RD Item Collection", {"collection": coll}), 4)
		ia_sync.refresh_mirrors()  # after an upgrade: all profiles, and nothing doubles
		self.assertEqual(frappe.db.count("RD Collection", {"mirror_of": "rdtestcoll"}), 1)

	def test_every_archive_org_collection_gets_a_page(self):
		from sok_resdesk import ia_sync

		frappe.db.set_single_value(
			"RD Settings", {"mirror_all_collections": 1, "mirror_min_books": 2, "mirror_skip": ""}
		)
		self.ia.sub = {f"{PREFIX}0001", f"{PREFIX}0002"}
		real = ia_sync._members

		def only_test_books():
			members, spelling = real()
			return {
				k: {b for b in v if b.startswith(PREFIX)}
				for k, v in members.items()
				if k.startswith("rdtest")
			}, spelling

		with mock.patch.object(ia_sync, "_members", side_effect=only_test_books):
			self.run_profile("Manual")
			sub_name = frappe.db.get_value("RD Collection", {"mirror_of": "rdtestsub"})
			top = frappe.db.get_value("RD Collection", {"mirror_of": "rdtestcoll"})
			self.assertTrue(sub_name and top)
			self.assertEqual(
				frappe.db.get_value("RD Collection", sub_name, ["title", "part_of"]), ("RD Test Sub", top)
			)
			self.assertEqual(frappe.db.count("RD Item Collection", {"collection": sub_name}), 2)
			# too small, or skipped in Settings: no page
			frappe.db.delete("RD Collection Rule", {"parent": sub_name})
			frappe.db.delete("RD Collection", sub_name)
			frappe.db.set_single_value("RD Settings", "mirror_skip", "RDTESTSUB")
			ia_sync.refresh_mirrors()
			self.assertFalse(frappe.db.exists("RD Collection", {"mirror_of": "rdtestsub"}))
			frappe.db.set_single_value("RD Settings", {"mirror_skip": "", "mirror_min_books": 3})
			ia_sync.refresh_mirrors()
			self.assertFalse(frappe.db.exists("RD Collection", {"mirror_of": "rdtestsub"}))

		# on the portal, the sub-collection is listed under its parent
		from sok_resdesk.portal import collection_cards

		frappe.db.set_single_value("RD Settings", "mirror_min_books", 1)
		with mock.patch.object(ia_sync, "_members", side_effect=only_test_books):
			ia_sync.refresh_mirrors()
		cards = {c.name: c for c in collection_cards()}
		sub_name = frappe.db.get_value("RD Collection", {"mirror_of": "rdtestsub"})
		self.assertEqual(cards[sub_name].part_of, top)
		self.assertEqual(cards[top].subcollections, 1)
