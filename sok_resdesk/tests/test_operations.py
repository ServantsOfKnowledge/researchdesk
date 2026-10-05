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
	"worker_nice",
	"ark_enabled",
	"ark_naan",
	"ark_shoulder",
	"preservation_root",
	"preserve_books",
	"preserve_page_images",
	"preservation_budget_gb",
	"fixity_days",
	"second_copy",
	"second_folder",
	"serve_from_copy",
	"search_romanised",
	"hold_page_text",
	"auto_books_first",
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
	frappe.db.set_value("RD Item", identifier, "page_order", 1)  # its page order is checked
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
		self.assertFalse(guide.checklist_mark("", "show")["hidden"])  # and it can be brought back
		self.assertEqual(guide.checklist()["steps"][0]["skipped"], True)  # without losing progress
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


class FakeMeili:
	"""Records what is sent to the search engine, in order."""

	books, pages = "rd_books", "rd_pages"

	def __init__(self):
		self.calls = []

	def add(self, index, documents, wait=False):
		self.calls.append(("add", index, len(documents)))

	def delete_by_filter(self, index, filter_):
		self.calls.append(("delete", index, filter_))

	def _req(self, method, path, **kwargs):
		return {"total": self.waiting}  # GET /tasks: how many wait

	waiting = 0


class TestIndexBuffer(OpsTestCase):
	def record(self, n):
		from sok_resdesk.catalogue import item_to_record

		return item_to_record(frappe.get_doc("RD Item", _item(n)))

	def test_books_go_first_then_old_pages_then_new_pages_in_big_tasks(self):
		from sok_resdesk.search import IndexBuffer

		fake = FakeMeili()
		buf = IndexBuffer(fake, flush_books=3)
		buf.PAGE_CHUNK = 5
		pages = [{"leaf": i, "label": "", "text": f"page {i}"} for i in range(4)]
		for n in (1, 2, 3):
			buf.add(self.record(n), pages, replace_pages=n != 1)
		self.assertTrue(buf.due)
		self.assertEqual(fake.calls, [])  # nothing is sent until the batch says so
		buf.flush()
		kinds = [c[:2] for c in fake.calls]
		self.assertEqual(kinds[0], ("add", "rd_books"))  # all three books in one task, first
		self.assertEqual(fake.calls[0][2], 3)
		self.assertEqual(kinds[1], ("delete", "rd_pages"))  # one delete for the two old page sets
		self.assertEqual(fake.calls[1][2].count(" OR "), 1)
		self.assertEqual([c[2] for c in fake.calls[2:]], [5, 5, 2])  # 12 pages in chunks of 5
		self.assertFalse(buf.due)
		for n in (1, 2, 3):
			self.assertTrue(frappe.db.get_value("RD Item", f"{PREFIX}{n:04d}", "indexed_on"))
			self.assertEqual(frappe.db.get_value("RD Item", f"{PREFIX}{n:04d}", "indexed_pages"), 4)

	def test_workers_hold_back_while_the_engine_is_behind(self):
		from sok_resdesk import search

		fake, naps = FakeMeili(), []

		def nap(seconds):
			naps.append(seconds)
			if len(naps) == 3:
				fake.waiting = 10  # the engine caught up

		fake.waiting = search.MAX_WAITING + 1
		self.assertEqual(search.wait_for_room(fake, sleep=nap), 30)
		fake.waiting = 0
		self.assertEqual(search.wait_for_room(fake, sleep=nap), 0)

	def test_books_not_sent_are_found(self):
		from sok_resdesk.search import index_missing

		name = _item(7)
		frappe.db.set_value("RD Item", name, "indexed_on", None)
		self.assertIn(name, index_missing())
		frappe.db.set_value("RD Item", name, "indexed_on", frappe.utils.now_datetime())
		self.assertNotIn(name, index_missing())


class TestWorkerPriority(OpsTestCase):
	def test_worker_takes_the_chosen_level(self):
		from sok_resdesk import priority

		frappe.set_user("Administrator")
		self.assertEqual(priority.set_worker_priority(10)["wanted"], 10)
		with (
			mock.patch("os.getpriority", return_value=19),
			mock.patch("os.setpriority") as setp,
		):
			self.assertEqual(priority.apply(force=True), 10)
		setp.assert_called_once_with(os.PRIO_PROCESS, 0, 10)

	def test_a_worker_that_may_not_lower_its_niceness_says_so(self):
		from sok_resdesk import priority

		frappe.set_user("Administrator")
		priority.set_worker_priority(0)
		with (
			mock.patch("os.getpriority", return_value=19),
			mock.patch("os.setpriority", side_effect=PermissionError("Operation not permitted")),
		):
			self.assertEqual(priority.apply(force=True), 19)  # stays where it was, no crash
		self.assertIn("Operation not permitted", priority.status()["refused"][0])

	def test_nothing_chosen_changes_nothing(self):
		from sok_resdesk import priority

		frappe.db.set_single_value("RD Settings", "worker_nice", "")
		with mock.patch("os.setpriority") as setp:
			priority.apply(force=True)
		setp.assert_not_called()

	def test_only_managers_and_only_known_levels(self):
		from sok_resdesk import priority

		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, priority.set_worker_priority, 7)
		self.assertRaises(frappe.ValidationError, priority.set_worker_priority, "fast")
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, priority.set_worker_priority, 10)
		frappe.set_user("Administrator")


class TestJobListIsReadOnly(OpsTestCase):
	def test_listing_jobs_does_not_clean_up_the_registries(self):
		"""Pause, Stop and the Jobs page list the running jobs from a web request. RQ's clean-up of
		the started registry runs failure callbacks with SIGALRM, which fails off the main thread
		("signal only works in main thread of the main interpreter"), so listing must not trigger it."""
		from rq.registry import StartedJobRegistry

		from sok_resdesk import jobs

		with (
			mock.patch.object(StartedJobRegistry, "get_job_ids", return_value=[]) as ids,
			mock.patch.object(StartedJobRegistry, "cleanup") as cleanup,
		):
			jobs._rq_jobs()
		self.assertTrue(ids.called)
		for call in ids.call_args_list:
			self.assertIs(call.kwargs.get("cleanup"), False)
		cleanup.assert_not_called()


class TestRetryByItself(OpsTestCase):
	def test_failed_runs_try_again_twice_then_wait_for_a_person(self):
		from frappe.utils import add_to_date, now_datetime

		from sok_resdesk import ingest

		profile = frappe.get_doc(
			{
				"doctype": "RD Ingest Profile",
				"profile_name": "rdtest retry",
				"source": "Internet Archive",
				"scope_type": "Collection",
				"ia_collection": "rdtestretry",
				"fetch_fulltext": 0,
			}
		).insert(ignore_permissions=True)
		run = frappe.get_doc(
			{"doctype": "RD Ingest Run", "profile": profile.name, "status": "Completed with Errors"}
		).insert(ignore_permissions=True)
		frappe.db.set_value("RD Ingest Run", run.name, "finished_on", add_to_date(now_datetime(), hours=-1))
		frappe.db.commit()
		self.addCleanup(lambda: frappe.db.delete("RD Ingest Run", run.name))
		self.addCleanup(lambda: frappe.db.delete("RD Ingest Profile", profile.name))
		with mock.patch("sok_resdesk.jobs.retry_run") as retry:
			for _ in range(4):
				ingest._retry_failed_runs(now_datetime(), add_to_date)
		self.assertEqual(retry.call_count, ingest.AUTO_RETRY)


class TestPermanentIdentifiers(OpsTestCase):
	def setUp(self):
		super().setUp()
		# straight into the database: Settings would (rightly) refuse the test NAAN
		frappe.db.set_single_value(
			"RD Settings", {"ark_enabled": 1, "ark_naan": "99999", "ark_shoulder": "b1"}
		)

	def test_new_books_get_an_ark_that_resolves(self):
		from sok_resdesk import identifiers
		from sok_resdesk.core import ark

		name = _item(21)
		pid = frappe.db.get_value("RD Item", name, "persistent_id")
		self.assertTrue(pid.startswith("ark:/99999/b1"))
		self.assertTrue(ark.parse(pid)["valid"])
		self.assertNotEqual(pid, frappe.db.get_value("RD Item", _item(22), "persistent_id"))
		where = identifiers.resolve(f"https://library.example/{pid}/n7")
		self.assertEqual((where["kind"], where["item"].name, where["leaf"]), ("book", name, 7))
		self.assertEqual(identifiers.resolve(pid[:-1] + ("b" if pid[-1] != "b" else "c"))["kind"], "unknown")
		# citations and records point at the permanent link
		from sok_resdesk.catalogue import get_record
		from sok_resdesk.core.citations import url_for

		self.assertEqual(
			url_for(get_record(name, check_access=False), "https://lib.example"), f"https://lib.example/{pid}"
		)

	def test_switched_off_nothing_is_minted_or_shown(self):
		from sok_resdesk import identifiers
		from sok_resdesk.catalogue import get_record

		name = _item(26)
		frappe.db.set_single_value("RD Settings", "ark_enabled", 0)
		self.assertIsNone(frappe.db.get_value("RD Item", _item(27), "persistent_id"))
		self.assertEqual(identifiers.assign_missing(), 0)
		self.assertEqual(get_record(name, check_access=False)["persistent_id"], "")  # minted before: hidden
		# an ARK already given out keeps resolving: a permanent link never breaks
		pid = frappe.db.get_value("RD Item", name, "persistent_id")
		self.assertEqual(identifiers.resolve(pid)["kind"], "book")

	def test_a_deleted_book_leaves_a_tombstone(self):
		from sok_resdesk import identifiers

		name = _item(23)
		pid = frappe.db.get_value("RD Item", name, "persistent_id")
		frappe.delete_doc("RD Item", name, force=True, ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.delete("RD Tombstone", {"ark": pid}))
		where = identifiers.resolve(pid)
		self.assertEqual(where["kind"], "tombstone")
		self.assertEqual(frappe.db.get_value("RD Tombstone", {"ark": pid}, "item_id"), name)

	def test_books_without_an_ark_get_one(self):
		from sok_resdesk import identifiers

		names = [_item(n) for n in (24, 25)]
		frappe.db.sql("update `tabRD Item` set persistent_id=null where name in %s", (tuple(names),))
		self.assertGreaterEqual(identifiers.assign_missing(), 2)
		self.assertTrue(all(frappe.db.get_value("RD Item", n, "persistent_id") for n in names))

	def test_switching_on_needs_a_real_naan_and_then_it_stays(self):
		frappe.db.set_single_value("RD Settings", {"ark_enabled": 0, "ark_naan": "", "ark_shoulder": "b1"})
		s = frappe.get_single("RD Settings")
		s.ark_enabled = 1
		self.assertRaises(frappe.ValidationError, s.save, ignore_permissions=True)  # no NAAN
		s.reload()
		s.ark_enabled, s.ark_naan = 1, "99999"
		self.assertRaises(frappe.ValidationError, s.save, ignore_permissions=True)  # the test NAAN
		s.reload()
		s.ark_enabled, s.ark_naan = 1, "12345"
		with mock.patch("sok_resdesk.identifiers.frappe.enqueue") as enqueue:
			s.save(ignore_permissions=True)
		self.assertEqual(enqueue.call_args.kwargs["job_id"], "resdesk-ark-assign")  # the books already here
		s = frappe.get_single("RD Settings")
		s.ark_naan = "54321"
		self.assertRaises(frappe.ValidationError, s.save, ignore_permissions=True)
		s.reload()
		s.ark_shoulder = "c2"
		self.assertRaises(frappe.ValidationError, s.save, ignore_permissions=True)


class TestOcrQuality(OpsTestCase):
	def test_books_are_scored_from_kept_page_text(self):
		from sok_resdesk import ocr
		from sok_resdesk.ingest import write_cached_pages

		name = _item(31)
		frappe.db.set_value("RD Item", name, {"has_page_text": 1, "ocr_quality": 0, "ocr_low_pages": 0})
		write_cached_pages(name, [{"leaf": 0, "label": "", "text": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು ಮತ್ತು ಪದಗಳು"}])
		self.assertIn(name, ocr.unscored())
		self.assertEqual(ocr.score_batch([name]), 1)
		self.assertGreaterEqual(frappe.db.get_value("RD Item", name, "ocr_quality"), 90)
		self.assertNotIn(name, ocr.unscored())

	def test_scoring_works_through_the_catalogue_in_one_job(self):
		from sok_resdesk import ocr
		from sok_resdesk.ingest import write_cached_pages

		kept, missing = _item(33), _item(34)
		for name in (kept, missing):
			frappe.db.set_value("RD Item", name, {"has_page_text": 1, "ocr_quality": 0, "ocr_low_pages": 0})
		write_cached_pages(kept, [{"leaf": 0, "label": "", "text": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು"}])
		# one job for the whole catalogue, however big (no flood of queued jobs)
		self.enqueued.clear()
		self.assertGreaterEqual(ocr.queue_scoring(), 2)
		self.assertEqual([m for m, _kw in self.enqueued], ["sok_resdesk.ocr.score_some"])
		with mock.patch(
			"sok_resdesk.ingest.read_cached_pages",
			side_effect=lambda n: (
				None if n == missing else [{"leaf": 0, "label": "", "text": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು"}]
			),
		):
			ocr.score_some()
		self.assertGreaterEqual(frappe.db.get_value("RD Item", kept, "ocr_quality"), 90)
		# no page text kept: marked, not taken again, scored when next indexed
		self.assertEqual(frappe.db.get_value("RD Item", missing, "ocr_low_pages"), -1)
		self.assertNotIn(missing, ocr.unscored())
		progress = ocr.progress()
		self.assertGreaterEqual(progress["scored"], 1)
		self.assertGreaterEqual(progress["no_text_kept"], 1)

	def test_indexing_records_the_quality(self):
		from sok_resdesk.search import IndexBuffer

		name = _item(32)
		from sok_resdesk.catalogue import item_to_record

		buf = IndexBuffer(FakeMeili())
		buf.add(
			item_to_record(frappe.get_doc("RD Item", name)),
			[{"leaf": 0, "label": "", "text": "ಕನ X ಡ ಾಕ ್ಕ ■■ ���"}],
		)
		buf.flush()
		self.assertLess(frappe.db.get_value("RD Item", name, "ocr_quality"), 50)
		self.assertEqual(frappe.db.get_value("RD Item", name, "ocr_low_pages"), 1)


class TestPreservation(OpsTestCase):
	"""Copies, checks and events on real files; only the archive.org download is replaced."""

	def setUp(self):
		super().setUp()
		self.root = tempfile.mkdtemp()
		frappe.db.set_single_value(
			"RD Settings", {"preservation_root": self.root, "preserve_books": "Every book", "fixity_days": 1}
		)
		self.content = {"book.pdf": b"%PDF-1.4 book", "book_meta.xml": b"<metadata/>"}

		def fetch(item_id, staging, with_images):
			out = {}
			for name, data in self.content.items():
				path = os.path.join(staging, name)
				with open(path, "wb") as f:
					f.write(data)
				out[name] = path
			return out

		p = mock.patch("sok_resdesk.preservation._fetch_ia", side_effect=fetch)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(lambda: frappe.db.delete("RD Preservation Event", {"item": ("like", f"{PREFIX}%")}))

	def test_copy_check_and_history(self):
		from sok_resdesk import preservation
		from sok_resdesk.core import ocfl

		name = _item(41)
		self.assertIn(name, preservation.wanted())
		first = preservation.preserve(name)
		self.assertEqual((first["version"], first["changed"]), ("v1", True))
		row = frappe.db.get_value("RD Item", name, ["preservation_status", "preserved_bytes"], as_dict=True)
		self.assertEqual(row.preservation_status, "Preserved")
		self.assertEqual(int(row.preserved_bytes), sum(len(v) for v in self.content.values()))
		self.assertNotIn(name, preservation.wanted())
		# the same files again: no new version, no new event
		self.assertFalse(preservation.preserve(name)["changed"])
		self.assertEqual(frappe.db.count("RD Preservation Event", {"item": name}), 1)
		# a changed file at the source: a new version holding only that file
		self.content["book.pdf"] = b"%PDF-1.4 book, corrected"
		self.assertEqual(preservation.preserve(name)["version"], "v2")
		# bit rot in the copy: the check finds it, records it and marks the book
		path = ocfl.head_files(self.root, name)["book_meta.xml"]
		with open(path, "wb") as f:
			f.write(b"<metadata>?</metadata>")
		with mock.patch("sok_resdesk.server.send_alert") as alert:
			result = preservation.audit()
		self.assertEqual(result["failed"], 1)
		alert.assert_called_once()
		self.assertEqual(frappe.db.get_value("RD Item", name, "preservation_status"), "Failed check")
		self.assertTrue(
			frappe.db.exists(
				"RD Preservation Event", {"item": name, "event_type": "Fixity check", "outcome": "Failure"}
			)
		)
		self.assertEqual(preservation.health_check()["state"], "bad")

	def test_only_collections_marked_preserve_when_asked(self):
		from sok_resdesk import preservation

		name = _item(42)
		frappe.db.set_single_value("RD Settings", "preserve_books", preservation.IN_COLLECTIONS)
		self.assertNotIn(name, preservation.wanted())
		frappe.db.set_single_value("RD Settings", "preserve_books", "Off")
		self.assertEqual(preservation.wanted(), [])


class FakeQueue(FakeMeili):
	"""A search engine with tasks waiting: the oldest page-text task is uid 100, the oldest book
	record task uid 105, both enqueued at `since`."""

	def __init__(self, since):
		super().__init__()
		self.since, self.cancelled = since, []
		self.uid = 200

	def add(self, index, documents, wait=False):
		super().add(index, documents)
		self.uid += 1
		return {"taskUid": self.uid}

	def _req(self, method, path, **kwargs):
		params = kwargs.get("params") or {}
		if method == "GET" and path == "/tasks" and params.get("reverse"):
			uid = 100 if params.get("indexUids") == self.pages else 105
			return {"results": [{"uid": uid, "enqueuedAt": self.since}]}
		if method == "POST" and path == "/tasks/cancel":
			self.cancelled.append(params["indexUids"])
			return {"taskUid": 999}
		return {"total": 0}

	def wait(self, task, timeout=60):
		return {"details": {"canceledTasks": 7}}


class TestSearchQueue(OpsTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", "hold_page_text", 0)
		# books sent before the waiting tasks (done) and among them (cancelled)
		self.done, self.waiting, self.unknown = _item(51), _item(52), _item(53)
		frappe.db.set_value("RD Item", self.done, {"indexed_pages": 10, "page_task": 90, "pages_pending": 0})
		frappe.db.set_value(
			"RD Item", self.waiting, {"indexed_pages": 10, "page_task": 120, "pages_pending": 0}
		)
		# sent before page tasks were recorded: matched by when it was sent
		frappe.db.set_value(
			"RD Item",
			self.unknown,
			{"indexed_pages": 10, "page_task": 0, "indexed_on": frappe.utils.now_datetime()},
		)
		import datetime as dt

		since = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
		self.fake = FakeQueue(since)
		p = mock.patch("sok_resdesk.search_queue.MeiliClient.from_settings", return_value=self.fake)
		p.start()
		self.addCleanup(p.stop)
		p = mock.patch("sok_resdesk.search_queue.time.sleep")
		p.start()
		self.addCleanup(p.stop)

	def pending(self, name):
		return frappe.db.get_value("RD Item", name, "pages_pending")

	def test_books_first_cancels_page_text_and_keeps_track_of_it(self):
		from sok_resdesk import search_queue

		frappe.set_user("Administrator")
		result = search_queue.books_first()
		self.assertEqual(self.fake.cancelled, [self.fake.pages])  # book records are left alone
		self.assertEqual(result["cancelled"], 7)
		self.assertEqual(
			(self.pending(self.done), self.pending(self.waiting), self.pending(self.unknown)), (0, 1, 1)
		)
		self.assertFalse(frappe.db.get_single_value("RD Settings", "hold_page_text"))  # back as it was
		self.assertTrue(any(m == "sok_resdesk.search_queue.send_pending" for m, _kw in self.enqueued))

	def test_cancelling_everything_loses_nothing(self):
		from sok_resdesk import jobs

		frappe.set_user("Administrator")
		result = jobs.cancel_search_tasks()
		self.assertEqual(self.fake.cancelled, [self.fake.pages, self.fake.books])
		self.assertEqual(self.pending(self.waiting), 1)
		# book records sent since the oldest cancelled one count as not sent (Send them)
		from sok_resdesk.search import index_missing

		self.assertIn(self.unknown, index_missing())
		self.assertGreaterEqual(result["unsent"], 1)

	def test_pending_page_text_is_sent_and_cleared_unless_held(self):
		from sok_resdesk import search_queue

		frappe.db.set_value("RD Item", self.waiting, {"pages_pending": 1, "has_page_text": 1})
		pages = [{"leaf": 0, "label": "", "text": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು"}]
		with (
			mock.patch("sok_resdesk.search.MeiliClient.from_settings", return_value=self.fake),
			mock.patch("sok_resdesk.ingest.fetch_pages", return_value=pages),
		):
			frappe.db.set_single_value("RD Settings", "hold_page_text", 1)
			self.assertEqual(search_queue.send_pending(), 0)  # held: nothing goes
			self.assertEqual(self.pending(self.waiting), 1)
			frappe.db.set_single_value("RD Settings", "hold_page_text", 0)
			search_queue.send_pending()
		self.assertEqual(self.pending(self.waiting), 0)
		self.assertEqual(frappe.db.get_value("RD Item", self.waiting, "page_task"), self.fake.uid)

	def test_held_page_text_waits_while_books_still_go(self):
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.search import IndexBuffer

		frappe.db.set_single_value("RD Settings", "hold_page_text", 1)
		buf = IndexBuffer(FakeMeili())
		buf.add(
			item_to_record(frappe.get_doc("RD Item", self.done)), [{"leaf": 0, "label": "", "text": "ಕನಕ"}]
		)
		buf.flush()
		self.assertEqual([c[1] for c in buf.client.calls], ["rd_books"])  # the book record only
		self.assertEqual(self.pending(self.done), 1)


class TestAutoBooksFirst(OpsTestCase):
	def engine(self, book_uid, page_uid, book_minutes_ago):
		import datetime as dt

		def at(minutes):
			return (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=minutes)).strftime(
				"%Y-%m-%dT%H:%M:%S.000000Z"
			)

		fake = FakeQueue(at(book_minutes_ago))
		tasks = {
			fake.books: {"uid": book_uid, "enqueuedAt": at(book_minutes_ago)},
			fake.pages: {"uid": page_uid, "enqueuedAt": at(60)},
		}
		fake._req = lambda method, path, **kw: (
			{"results": [tasks[kw["params"]["indexUids"]]]}
			if kw.get("params", {}).get("reverse")
			else {"total": 0}
		)
		return fake

	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("RD Settings", {"auto_books_first": 1, "hold_page_text": 0})
		frappe.cache.delete_value("resdesk:auto-books-first")
		self.addCleanup(frappe.cache.delete_value, "resdesk:auto-books-first")
		p = mock.patch("sok_resdesk.search_queue.cancel_waiting", return_value={"cancelled": 3, "books": 2})
		self.cancel = p.start()
		self.addCleanup(p.stop)

	def test_a_book_stuck_behind_page_text_goes_first_by_itself(self):
		from sok_resdesk import search_queue

		self.assertIsNotNone(
			search_queue.auto_books_first(self.engine(book_uid=500, page_uid=100, book_minutes_ago=20))
		)
		self.cancel.assert_called_once_with(include_books=False)
		# not again for half an hour
		self.assertIsNone(search_queue.auto_books_first(self.engine(500, 100, 20)))
		self.assertEqual(self.cancel.call_count, 1)

	def test_left_alone_when_not_stuck_or_switched_off(self):
		from sok_resdesk import search_queue

		self.assertIsNone(search_queue.auto_books_first(self.engine(500, 100, 5)))  # not waiting long yet
		self.assertIsNone(
			search_queue.auto_books_first(self.engine(100, 500, 20))
		)  # no page text ahead of it
		frappe.db.set_single_value("RD Settings", "auto_books_first", 0)
		self.assertIsNone(search_queue.auto_books_first(self.engine(500, 100, 20)))
		self.cancel.assert_not_called()


class TestPageReader(OpsTestCase):
	def setUp(self):
		super().setUp()
		from sok_resdesk.ingest import write_cached_pages

		self.name = _item(61)
		frappe.db.set_value(
			"RD Item", self.name, {"has_page_text": 1, "page_count": 12, "visibility": "Public"}
		)
		write_cached_pages(
			self.name,
			[
				{"leaf": 4, "label": "1", "text": "ಮೊದಲ ಪುಟ"},
				{"leaf": 5, "label": "2", "text": "ಎರಡನೆಯ ಪುಟ"},
			],
		)

	def test_a_page_with_its_image_text_and_number(self):
		from sok_resdesk import api

		frappe.set_user("Guest")
		d = api.page(self.name, 5)
		self.assertEqual((d["leaf"], d["label"], d["text"], d["last"]), (5, "2", "ಎರಡನೆಯ ಪುಟ", 11))
		self.assertTrue(d["image"].endswith(f"/download/{self.name}/page/n5.jpg"))
		blank = api.page(self.name, 7)  # a page with no text still has its image
		self.assertEqual((blank["text"], blank["has_text"]), ("", True))
		self.assertEqual(api.page(self.name, 999)["leaf"], 11)  # past the end: the last page

	def test_members_only_text_needs_a_login(self):
		from sok_resdesk import api

		frappe.db.set_value("RD Item", self.name, "visibility", "Login to read")
		frappe.set_user("Guest")
		self.assertEqual(api.page(self.name, 5), {"login_needed": True})

	def test_cite_a_page(self):
		from sok_resdesk import api

		frappe.set_user("Guest")
		c = api.cite_page(self.name, 5, "2")
		self.assertEqual(c["page"], "p. 2")
		self.assertTrue(c["url"].endswith(f"/library/item/{self.name}?page=5&view=text"))
		self.assertIn("SP  - 2", c["formats"]["ris"])


class TestAnnotations(OpsTestCase):
	A, B = "rdtest-reader-a@example.com", "rdtest-reader-b@example.com"
	TEXT = "Kanakadasa sang of Udupi; Udupi Krishna faced him through the window."

	def setUp(self):
		super().setUp()
		from sok_resdesk.ingest import write_cached_pages

		for email in (self.A, self.B):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": email.split("@")[0],
						"send_welcome_email": 0,
						"user_type": "Website User",
					}
				).insert(ignore_permissions=True)
		self.book = _item(71)
		frappe.db.set_value("RD Item", self.book, {"has_page_text": 1, "visibility": "Public"})
		write_cached_pages(self.book, [{"leaf": 2, "label": "1", "text": self.TEXT}])
		frappe.db.commit()
		self.addCleanup(self.cleanup)

	def cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Annotation", {"item": self.book})
		frappe.db.delete("RD Research Group Member", {"parent": "rdtest circle"})
		frappe.db.delete("RD Research Group", {"name": "rdtest circle"})
		frappe.db.commit()

	def add(self, user, **kw):
		from sok_resdesk import annotations

		frappe.set_user(user)
		start = kw.pop("start", self.TEXT.index("Udupi Krishna"))
		args = {
			"kind": "Comment",
			"body": "a note",
			"start": start,
			"end": start + 5,
			"page_label": "1",
			**kw,
		}
		return annotations.add(self.book, 2, **args)

	def seen_by(self, user):
		from sok_resdesk import annotations

		frappe.set_user(user)
		return {n["body"] for n in annotations.page_notes(self.book, 2)["notes"]}

	def test_who_sees_what(self):
		from sok_resdesk import annotations

		self.add(self.A, body="private")
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "RD Research Group",
				"group_name": "rdtest circle",
				"members": [{"user": self.A}, {"user": self.B}],
			}
		).insert(ignore_permissions=True)
		self.add(self.A, body="for the circle", visibility="Group", research_group="rdtest circle")
		public = self.add(self.A, body="for everyone", visibility="Public")
		self.assertEqual(public["review_status"], "Pending")
		self.add(self.B, kind="OCR error", body="Udupi is misread")
		self.assertEqual(self.seen_by(self.A), {"private", "for the circle", "for everyone"})
		self.assertEqual(self.seen_by(self.B), {"for the circle", "Udupi is misread"})
		self.assertEqual(self.seen_by("Guest"), set())
		# managers see what waits for review and every OCR error report
		self.assertEqual(self.seen_by("Administrator"), {"for everyone", "Udupi is misread"})
		frappe.set_user("Administrator")
		annotations.review(public["name"], "Approved")
		self.assertIn("for everyone", self.seen_by(self.B))
		self.assertIn("for everyone", self.seen_by("Guest"))
		w3c = frappe.parse_json(annotations.collection(self.book).get_data(as_text=True))
		self.assertEqual([i["body"]["value"] for i in w3c["items"]], ["for everyone"])

	def test_only_readers_add_and_only_authors_change(self):
		from sok_resdesk import annotations

		frappe.set_user("Guest")
		self.assertRaises(
			frappe.PermissionError, annotations.add, self.book, 2, "Comment", "x", start=0, end=5
		)
		note = self.add(self.A, body="mine")
		frappe.set_user(self.B)
		self.assertRaises(frappe.PermissionError, annotations.edit, note["name"], body="not yours")
		self.assertRaises(frappe.PermissionError, annotations.remove, note["name"])
		frappe.set_user(self.A)
		self.assertEqual(annotations.edit(note["name"], body="changed")["body"], "changed")
		# a group the author isn't in is refused; an empty comment too; links must be web addresses
		self.assertRaises(frappe.ValidationError, self.add, self.A, visibility="Group", research_group="nope")
		self.assertRaises(frappe.ValidationError, self.add, self.A, body="  ")
		self.assertRaises(frappe.ValidationError, self.add, self.A, kind="Link", link="javascript:alert(1)")
		self.assertRaises(frappe.ValidationError, self.add, self.A, start=5, end=500)
		annotations.remove(note["name"])
		self.assertFalse(frappe.db.exists("RD Annotation", note["name"]))

	def test_notes_follow_their_words_after_the_text_is_corrected(self):
		from sok_resdesk import annotations
		from sok_resdesk.ingest import write_cached_pages

		note = self.add(self.A, body="the second Udupi")
		write_cached_pages(self.book, [{"leaf": 2, "label": "1", "text": "Corrected: " + self.TEXT}])
		frappe.set_user(self.A)
		moved = annotations.page_notes(self.book, 2)["notes"][0]
		self.assertEqual(moved["pos_start"], note["pos_start"] + len("Corrected: "))
		self.assertFalse(moved["detached"])
		write_cached_pages(self.book, [{"leaf": 2, "label": "1", "text": "Nothing like it any more."}])
		self.assertTrue(annotations.page_notes(self.book, 2)["notes"][0]["detached"])

	def test_my_notes_and_exports(self):
		from sok_resdesk import annotations

		self.add(self.A, body="see the 1890 edition", tags="edition, udupi")
		self.add(self.A, region="10,20,30,40", body="a stamp")
		frappe.set_user(self.A)
		found = annotations.mine(q="1890")["notes"]
		self.assertEqual([n["body"] for n in found], ["see the 1890 edition"])
		self.assertTrue(found[0]["url"].endswith(f"{self.book}?page=2&view=text"))
		self.assertEqual(found[0]["page"], "p. 1")
		md = annotations.export("markdown").get_data(as_text=True)
		self.assertIn("“Udupi”: see the 1890 edition #edition #udupi", md)
		self.assertIn("(a region of the page image): a stamp", md)
		csv_text = annotations.export("csv").get_data(as_text=True)
		self.assertEqual(csv_text.count("\n"), 3)
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, annotations.mine)


class TestProofreading(OpsTestCase):
	P, Q, R = "rdtest-proof-p@example.com", "rdtest-proof-q@example.com", "rdtest-reader-r@example.com"
	GOOD = "Kanakadasa sang of Udupi; Udupi Krishna faced him through the window. " * 3
	BAD = "K@n#k ~~ ds;; 1l|I ,,.. ^^ %% Ud!p| Kr~shn@ f@c#d h|m" * 3

	def setUp(self):
		super().setUp()
		from sok_resdesk.ingest import write_cached_pages

		for email in (self.P, self.Q, self.R):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": email.split("@")[0],
						"send_welcome_email": 0,
						"user_type": "Website User",
					}
				).insert(ignore_permissions=True)
				if "proof" in email:
					user.add_roles("ResDesk Proofreader")
		self.book = _item(81)
		frappe.db.set_value(
			"RD Item", self.book, {"has_page_text": 1, "visibility": "Public", "on_archive_org": 1}
		)
		write_cached_pages(
			self.book,
			[
				{"leaf": 1, "label": "1", "text": self.BAD},
				{"leaf": 2, "label": "2", "text": self.GOOD},
				{"leaf": 3, "label": "3", "text": self.BAD},
			],
		)
		patcher = mock.patch("sok_resdesk.search.reindex_pages")
		self.reindexed = patcher.start()
		self.addCleanup(patcher.stop)
		frappe.db.commit()
		self.addCleanup(self.cleanup)

	def cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Page Text", {"item": ("like", f"{PREFIX}%")})
		frappe.db.commit()

	def text_of(self, leaf):
		from sok_resdesk.ingest import fetch_pages

		return {p["leaf"]: p["text"] for p in fetch_pages(self.book)}[leaf]

	def test_corrections_overlay_the_text_and_validation_needs_a_second_person(self):
		from sok_resdesk import pagetext

		frappe.set_user(self.P)
		self.assertEqual(pagetext.save_page(self.book, 1, "Corrected page one")["status"], "Proofread")
		self.assertEqual(self.text_of(1), "Corrected page one")
		self.assertEqual(self.text_of(2), self.GOOD)  # other pages keep archive.org's text
		self.assertEqual(frappe.db.get_value("RD Item", self.book, "pages_proofread"), 1)
		self.assertTrue(self.reindexed.called)
		# the proofreader can't validate their own page
		self.assertRaises(
			frappe.ValidationError, pagetext.save_page, self.book, 1, "Corrected page one", validate=1
		)
		frappe.set_user(self.Q)
		# a second person who changes the text makes a new proofread version instead
		changed = pagetext.save_page(self.book, 1, "Corrected page one!", validate=1)
		self.assertEqual(changed["status"], "Proofread")
		frappe.set_user(self.P)
		done = pagetext.save_page(self.book, 1, "Corrected page one!", validate=1)
		self.assertEqual(done["status"], "Validated")
		versions = pagetext.history(self.book, 1)["versions"]
		self.assertEqual([v.status for v in versions], ["Validated", "Proofread"])
		self.assertEqual(versions[0].validated_by, self.P)
		# an earlier version comes back as a new one: the history keeps everything
		pagetext.restore(versions[1].name)
		self.assertEqual(self.text_of(1), "Corrected page one")
		self.assertEqual(len(pagetext.history(self.book, 1)["versions"]), 3)
		self.assertEqual(frappe.db.count("RD Page Text", {"item": self.book, "is_current": 1}), 1)

	def test_only_proofreaders(self):
		from sok_resdesk import pagetext, reocr

		for user in (self.R, "Guest"):
			frappe.set_user(user)
			self.assertRaises(frappe.PermissionError, pagetext.save_page, self.book, 1, "x")
			self.assertRaises(frappe.PermissionError, pagetext.history, self.book, 1)
			self.assertRaises(frappe.PermissionError, reocr.ocr_page, self.book, 1)
		frappe.set_user(self.P)
		self.assertRaises(frappe.PermissionError, reocr.enqueue_book, self.book)

	def test_ocr_of_one_page_in_zones_comes_back_to_its_proofreader(self):
		from sok_resdesk import reocr

		frappe.set_user(self.P)
		zones = [
			{"x": 50, "y": 0, "w": 50, "h": 100, "kind": "text"},
			{"x": 0, "y": 0, "w": 50, "h": 100, "kind": "text"},
		]
		with mock.patch("sok_resdesk.core.ocr_engine.available", return_value=["eng"]):
			key = reocr.ocr_page(self.book, 1, zones)["key"]
		self.assertEqual(reocr.ocr_result(key)["status"], "queued")
		method, kw = self.enqueued[-1]
		self.assertEqual(method, "sok_resdesk.reocr.ocr_page_job")
		self.assertEqual([z["x"] for z in kw["zones"]], [50, 0])  # the proofreader's reading order
		seen = {}

		def read_page(image, zones, models):
			seen["zones"] = zones
			return {"text": "right\n\nleft", "zones": [{"zone": z, "text": ""} for z in zones]}

		with (
			mock.patch("sok_resdesk.reocr.page_image", return_value=b"png"),
			mock.patch("sok_resdesk.reocr.models_for", return_value="eng"),
			mock.patch("sok_resdesk.core.ocr_engine.read_page", side_effect=read_page),
		):
			reocr.ocr_page_job(**{k: v for k, v in kw.items() if k not in ("queue", "timeout")})
		result = reocr.ocr_result(key)
		self.assertEqual((result["status"], result["text"]), ("done", "right\n\nleft"))
		self.assertEqual(len(seen["zones"]), 2)
		frappe.set_user(self.Q)
		self.assertRaises(frappe.PermissionError, reocr.ocr_result, key)

	def test_book_reocr_keeps_better_text_and_never_touches_proofread_pages(self):
		from sok_resdesk import pagetext, reocr
		from sok_resdesk.core import ocr_engine

		frappe.set_user(self.P)
		pagetext.save_page(self.book, 3, "Proofread by a person")
		frappe.set_user("Administrator")
		asked = []

		def page_image(item_id, leaf):
			if leaf == 0:
				raise ocr_engine.OcrError("no image")
			asked.append(leaf)
			return str(leaf).encode()

		def read_page(image, zones, models):
			return {"text": self.GOOD.replace("Udupi", "Udupi!"), "zones": []}

		with (
			mock.patch("sok_resdesk.reocr.page_image", side_effect=page_image),
			mock.patch("sok_resdesk.reocr.models_for", return_value="eng"),
			mock.patch("sok_resdesk.core.ocr_engine.read_page", side_effect=read_page),
		):
			counts = reocr.reocr_book(self.book, "Two columns")
		self.assertEqual(asked, [1, 2])
		self.assertEqual(counts, {"read": 2, "improved": 1, "failed": 1})
		self.assertIn("Udupi!", self.text_of(1))  # garbled text replaced
		self.assertEqual(self.text_of(2), self.GOOD)  # good text kept
		self.assertEqual(self.text_of(3), "Proofread by a person")
		row = frappe.db.get_value(
			"RD Page Text",
			{"item": self.book, "leaf": 1, "is_current": 1},
			["source", "status"],
			as_dict=True,
		)
		self.assertEqual((row.source, row.status), ("Re-OCR", "Machine"))
		self.assertIn("better", frappe.db.get_value("RD Item", self.book, "reocr_state"))

	def test_worst_books_first(self):
		from sok_resdesk import reocr

		worse, done = _item(82), _item(83)
		frappe.db.set_value("RD Item", self.book, {"ocr_quality": 60})
		frappe.db.set_value("RD Item", worse, {"ocr_quality": 20, "on_archive_org": 1})
		frappe.db.set_value("RD Item", done, {"ocr_quality": 10, "on_archive_org": 1, "reocr_state": "x"})
		with mock.patch("sok_resdesk.core.ocr_engine.available", return_value=["eng"]):
			reocr.enqueue_worst(500, "Whole page")
		names = [n for n in self.enqueued[-1][1]["names"] if n.startswith(PREFIX)]
		self.assertEqual(names, [worse, self.book])
		self.assertEqual(frappe.db.get_value("RD Item", worse, "reocr_state"), "waiting to be read again")

	def test_work_list(self):
		from frappe.website.serve import get_response_content

		from sok_resdesk import pagetext

		frappe.db.set_value("RD Item", self.book, {"published": 1, "ocr_quality": 40})
		frappe.set_user(self.P)
		pagetext.save_page(self.book, 1, "Corrected page one")
		frappe.set_user(self.Q)
		html = get_response_content("library/proofread")
		self.assertIn("Operations test book 81", html)
		self.assertIn("Waiting for a second look", html)
		frappe.set_user(self.R)
		self.assertNotIn("Waiting for a second look", get_response_content("library/proofread"))


class TestPageOrder(OpsTestCase):
	"""archive.org's OCR counts a colour card the book doesn't show: texts move to their image."""

	SCAN = (
		b"<book><pageData>"
		b"<page leafNum='0'><addToAccessFormats>false</addToAccessFormats></page>"
		b"<page leafNum='1'><addToAccessFormats>true</addToAccessFormats></page>"
		b"<page leafNum='2'><addToAccessFormats>true</addToAccessFormats></page>"
		b"</pageData></book>"
	)

	class IA:
		def __init__(self, scan):
			self.scan = scan

		def metadata(self, identifier):
			return {"metadata": {}, "files": [{"name": f"{identifier}_scandata.xml"}]}

		def scan_leaves(self, identifier, files):
			from sok_resdesk.core import scandata

			return scandata.parse(self.scan)

		def page_texts(self, identifier, page_numbers=None, files=None):
			from sok_resdesk.core import scandata

			return scandata.pages(
				["card", "Title page", "Chapter one"], page_numbers, self.scan_leaves(identifier, files)
			)

	def test_old_order_is_put_right_and_notes_follow_their_words(self):
		from sok_resdesk.ingest import fetch_pages, write_cached_pages

		book = _item(91)
		frappe.db.set_value("RD Item", book, {"has_page_text": 1, "visibility": "Public", "page_order": 0})
		# as cached before: counted by OCR page, the colour card being page 0
		write_cached_pages(
			book,
			[
				{"leaf": 0, "label": "", "text": "card"},
				{"leaf": 1, "label": "", "text": "Title page"},
				{"leaf": 2, "label": "", "text": "Chapter one"},
			],
		)
		note = frappe.get_doc(
			{
				"doctype": "RD Annotation",
				"item": book,
				"leaf": 2,
				"kind": "Comment",
				"body": "on chapter one",
				"exact": "Chapter",
				"pos_start": 0,
				"pos_end": 7,
			}
		).insert(ignore_permissions=True)
		region = frappe.get_doc(
			{
				"doctype": "RD Annotation",
				"item": book,
				"leaf": 2,
				"kind": "Comment",
				"body": "a stamp",
				"region": "1,1,10,10",
			}
		).insert(ignore_permissions=True)
		with mock.patch("sok_resdesk.ingest.client", return_value=self.IA(self.SCAN)):
			pages = fetch_pages(book)
		self.assertEqual([(p["leaf"], p["text"]) for p in pages], [(0, "Title page"), (1, "Chapter one")])
		self.assertEqual(frappe.db.get_value("RD Item", book, "page_order"), 1)
		self.assertEqual(frappe.db.get_value("RD Annotation", note.name, "leaf"), 1)
		self.assertEqual(frappe.db.get_value("RD Annotation", region.name, "leaf"), 2)  # drawn on the image
		self.assertIn("sok_resdesk.page_order.reindex_book", [m for m, _ in self.enqueued])
		frappe.db.delete("RD Annotation", {"item": book})

	def test_books_with_nothing_left_out_are_only_marked(self):
		from sok_resdesk.ingest import fetch_pages, write_cached_pages

		book = _item(92)
		frappe.db.set_value("RD Item", book, {"has_page_text": 1, "page_order": 0})
		write_cached_pages(book, [{"leaf": 0, "label": "", "text": "Title page"}])
		with mock.patch(
			"sok_resdesk.ingest.client",
			return_value=self.IA(b"<book><pageData><page leafNum='0'/></pageData></book>"),
		):
			self.assertEqual(fetch_pages(book)[0]["leaf"], 0)
		self.assertEqual(frappe.db.get_value("RD Item", book, "page_order"), 1)
		self.assertNotIn("sok_resdesk.page_order.reindex_book", [m for m, _ in self.enqueued])


class TestPeople(OpsTestCase):
	MANAGER, OTHER = "rdtest-manager@example.com", "rdtest-person@example.com"

	def setUp(self):
		super().setUp()
		for email in (self.MANAGER, self.OTHER):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": email.split("@")[0],
						"send_welcome_email": 0,
					}
				).insert(ignore_permissions=True)
		frappe.get_doc("User", self.MANAGER).add_roles("ResDesk Manager")
		frappe.db.commit()
		self.addCleanup(self.cleanup)

	def cleanup(self):
		frappe.set_user("Administrator")
		for email in (self.MANAGER, self.OTHER, "rdtest-new1@example.com", "rdtest-new2@example.com"):
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_roles_given_taken_and_guarded(self):
		from sok_resdesk import people

		frappe.set_user(self.MANAGER)
		roles = {r["role"]: r for r in people.overview()["roles"]}
		self.assertFalse(roles["System Manager"]["can_grant"])
		self.assertIn("ResDesk Proofreader", people.set_role(self.OTHER, "ResDesk Proofreader", 1)["roles"])
		self.assertIn(self.OTHER, [u.name for u in people.users(role="ResDesk Proofreader")])
		self.assertNotIn(
			"ResDesk Proofreader", people.set_role(self.OTHER, "ResDesk Proofreader", 0)["roles"]
		)
		# staff role → Desk account
		self.assertTrue(people.set_role(self.OTHER, "ResDesk Cataloguer", 1)["desk"])
		self.assertRaises(frappe.PermissionError, people.set_role, self.OTHER, "System Manager", 1)
		self.assertRaises(frappe.ValidationError, people.set_role, self.MANAGER, "ResDesk Manager", 0)
		self.assertRaises(frappe.ValidationError, people.set_role, "Administrator", "ResDesk Reader", 1)
		self.assertRaises(frappe.ValidationError, people.set_role, self.OTHER, "Accounts User", 1)
		self.assertRaises(frappe.ValidationError, people.set_enabled, self.MANAGER, 0)
		self.assertEqual(people.set_enabled(self.OTHER, 0)["enabled"], 0)
		self.assertNotIn(self.OTHER, [u.name for u in people.users(q="rdtest-person")])
		self.assertIn(self.OTHER, [u.name for u in people.users(q="rdtest-person", show_disabled=1)])
		people.set_enabled(self.OTHER, 1)
		frappe.set_user(self.OTHER)
		self.assertRaises(frappe.PermissionError, people.overview)

	def test_invite(self):
		from sok_resdesk import people

		frappe.set_user(self.MANAGER)
		out = people.invite(
			"rdtest-new1@example.com, rdtest-new2@example.com\n" + self.OTHER,
			'["ResDesk Reader"]',
			send_welcome=0,
		)
		self.assertEqual(sorted(out["made"]), ["rdtest-new1@example.com", "rdtest-new2@example.com"])
		self.assertEqual(out["updated"], [self.OTHER])
		self.assertIn("ResDesk Reader", frappe.get_roles("rdtest-new1@example.com"))
		self.assertEqual(frappe.db.get_value("User", "rdtest-new1@example.com", "user_type"), "Website User")
		self.assertRaises(frappe.ValidationError, people.invite, "rdtest-new1@example.com", "[]")


class TestDashboardAndStatistics(OpsTestCase):
	def test_numbers_and_statistics_choice(self):
		from sok_resdesk import analytics, dashboard

		_item(95)
		frappe.db.set_value("RD Item", f"{PREFIX}0095", {"published": 1, "ocr_quality": 40})
		out = dashboard.numbers(refresh=1)
		cards = {c["label"]: c for g in out["groups"] for c in g["cards"]}
		self.assertGreaterEqual(cards["Books on the portal"]["value"], 1)
		self.assertIn("Readers", cards)

		def choose(**values):
			# a fresh copy each time: saving settings updates them (branding, sign-up, statistics)
			s = frappe.get_single("RD Settings")
			s.update(values)
			s.save()

		self.assertRaises(
			frappe.ValidationError,
			choose,
			analytics_provider="PostHog",
			analytics_host="http://insecure.example",
			analytics_key="phc_x",
		)
		choose(
			analytics_provider="PostHog", analytics_host="https://eu.i.posthog.com/", analytics_key="phc_x"
		)
		self.assertEqual(
			analytics.config(), {"provider": "PostHog", "host": "https://eu.i.posthog.com", "key": "phc_x"}
		)
		choose(analytics_provider="Built-in")
		self.assertEqual(analytics.config(), {"provider": ""})
		ws = frappe.get_single("Website Settings")
		if ws.meta.has_field("enable_view_tracking"):
			self.assertEqual(int(ws.enable_view_tracking), 1)
			titles = [g["title"] for g in dashboard.numbers(refresh=1)["groups"]]
			self.assertIn("Portal use", titles)
		choose(analytics_provider="Off")


class TestSecondCopy(OpsTestCase):
	"""The second copy, repairs both ways, serving from our copy and BagIt, on real files."""

	def setUp(self):
		super().setUp()
		self.root, self.second = tempfile.mkdtemp(), tempfile.mkdtemp()
		frappe.db.set_single_value(
			"RD Settings",
			{
				"preservation_root": self.root,
				"preserve_books": "Every book",
				"fixity_days": 1,
				"second_copy": "Folder",
				"second_folder": self.second,
			},
		)
		content = {"book.pdf": b"%PDF-1.4 book", "book_meta.xml": b"<metadata/>"}

		def fetch(item_id, staging, with_images):
			out = {}
			for name, data in content.items():
				path = os.path.join(staging, f"{item_id}.pdf" if name == "book.pdf" else name)
				with open(path, "wb") as f:
					f.write(data)
				out[os.path.basename(path)] = path
			return out

		p = mock.patch("sok_resdesk.preservation._fetch_ia", side_effect=fetch)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(lambda: frappe.db.delete("RD Preservation Event", {"item": ("like", f"{PREFIX}%")}))

	def _rot(self, root, name, file="book_meta.xml"):
		from sok_resdesk.core import ocfl

		with open(ocfl.head_files(root, name)[file], "ab") as f:
			f.write(b"rot")

	def test_second_copy_and_repairs_both_ways(self):
		from sok_resdesk import preservation

		name = _item(61)
		preservation.preserve(name)  # the second copy follows the first at once
		row = frappe.db.get_value(
			"RD Item", name, ["second_copy_status", "second_copy_version", "copies"], as_dict=True
		)
		self.assertEqual(
			(row.second_copy_status, row.second_copy_version, row.copies), ("Copied", "v1", "2 of 2 verified")
		)
		self.assertNotIn(name, preservation.wanted_second())
		# the first copy rots: rebuilt from the second
		self._rot(self.root, name)
		result = preservation.check(name)
		self.assertTrue(result["ok"])
		self.assertTrue(
			frappe.db.exists(
				"RD Preservation Event", {"item": name, "event_type": "Repair", "outcome": "Success"}
			)
		)
		self.assertEqual(frappe.db.get_value("RD Item", name, "preservation_status"), "Preserved")
		# the second copy rots: rebuilt from the first
		self._rot(self.second, name)
		self.assertTrue(preservation.check(name)["second"]["ok"])
		self.assertEqual(frappe.db.count("RD Preservation Event", {"item": name, "event_type": "Repair"}), 2)
		# both rot: nothing to rebuild from, both marked
		self._rot(self.root, name)
		self._rot(self.second, name)
		preservation.check(name)
		row = frappe.db.get_value(
			"RD Item", name, ["preservation_status", "second_copy_status", "copies"], as_dict=True
		)
		self.assertEqual(
			(row.preservation_status, row.second_copy_status, row.copies),
			("Failed check", "Failed check", "0 of 2 verified"),
		)
		self.assertEqual(preservation.health_check()["state"], "bad")
		# the second folder can't be the first one, or inside it
		s = frappe.get_single("RD Settings")
		s.second_folder = os.path.join(self.root, "inside")
		self.assertRaises(frappe.ValidationError, s.save)

	def test_serving_from_our_copy_and_bagit(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		from sok_resdesk import api, preservation
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.core import bagit

		name = _item(62)
		frappe.db.set_value("RD Item", name, {"visibility": "Public", "access_status": "Open"})
		preservation.preserve(name)
		preservation.serve_from_copy(name, 1)
		record = item_to_record(frappe.get_doc("RD Item", name))
		self.assertFalse(record["on_archive_org"])
		self.assertIn(f"sok_resdesk.api.file?item_id={name}&name={name}.pdf", record["pdf_url"])
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())
		frappe.local.request_ip = "127.0.0.1"  # the endpoint is rate-limited by address
		response = api.file(name, f"{name}.pdf")
		response.direct_passthrough = False
		self.assertEqual(response.get_data(), b"%PDF-1.4 book")
		self.assertRaises(frappe.PageDoesNotExistError, api.file, name, "book_meta.xml")
		self.assertTrue(
			frappe.db.exists("RD Preservation Event", {"item": name, "event_type": "Access from copy"})
		)
		# no longer on archive.org and no longer served: it leaves the portal
		frappe.db.set_value("RD Item", name, "removed_from_source", 1)
		preservation.serve_from_copy(name, 0)
		self.assertEqual(frappe.db.get_value("RD Item", name, "published"), 0)
		# a bag of the book, valid, in <first copy>/exports
		made = preservation.export_book(name)
		path = os.path.join(self.root, "exports", made["file"])
		self.assertEqual(bagit.validate(path, name), [])
		self.assertIn(made["file"], [x["file"] for x in preservation.exports()])
		self.assertRaises(frappe.PermissionError, preservation.download_export, "../secret.zip")

	def test_s3_library_is_in_the_image(self):
		"""An S3 second copy needs boto3, installed with Research Desk (pyproject.toml)."""
		import importlib.util

		self.assertIsNotNone(importlib.util.find_spec("boto3"), "boto3 is missing from the image")


class TestRomanisedSearch(OpsTestCase):
	"""Romanised words, OR and phrases against the real search engine, on test indexes."""

	BOOKS = [
		("rs1", "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು", "Kannada", "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು ಮೊದಲನೆಯ ಭಾಗ"),
		("rs2", "ವಚನ ಸಂಪುಟ", "Kannada", "ಬಸವಣ್ಣನವರ ವಚನಗಳು ಕರ್ನಾಟಕ"),
		("rs3", "ಪುರಂದರ ದಾಸರ ಪದಗಳು", "Kannada", "ಪುರಂದರ ದಾಸರು ಕರ್ನಾಟಕ ಸಂಗೀತ"),
		("rs4", "History of Kannada literature", "English", "Kanakadasa and Purandaradasa"),
	]

	def setUp(self):
		super().setUp()
		from sok_resdesk import search

		real = search.MeiliClient.from_settings()
		self.client = search.MeiliClient(
			real.url, real.session.headers.get("Authorization", "")[7:], "rdtestsearch"
		)
		self.client.setup()
		docs = [
			{
				"id": i,
				"item_id": i,
				"title": t,
				"language_label": lang,
				"visibility": "Public",
				"text_excerpt": x,
			}
			for i, t, lang, x in self.BOOKS
		]
		self.client.wait(
			self.client._req("POST", f"/indexes/{self.client.books}/documents", json=docs), timeout=60
		)
		p = mock.patch("sok_resdesk.search.MeiliClient.from_settings", return_value=self.client)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(self.drop)

	def drop(self):
		for index in (self.client.books, self.client.pages):
			try:
				self.client._req("DELETE", f"/indexes/{index}")
			except Exception:
				pass

	def found(self, q, **filters):
		from sok_resdesk import search

		r = search.search(q, "books", filters or {}, 1, 20)
		return {h["item_id"] for h in r["hits"]}, [a["q"] for a in r.get("also") or []]

	def test_latin_letters_find_indic_spellings(self):
		ids, also = self.found("kanakadasa")
		self.assertEqual(ids, {"rs1", "rs4"})  # the Kannada book, and the English one by its own words
		self.assertEqual(also, ["ಕನಕದಾಸ"])
		ids, also = self.found("karnataka sangeeta")
		self.assertIn("rs3", ids)
		self.assertIn("ಕರ್ನಾಟಕ ಸಂಗೀತ", also)
		self.assertEqual(self.found("history")[1], [])  # an English word gets no invented spelling

	def test_or_phrases_and_exclusions(self):
		self.assertEqual(self.found("purandara OR vachana")[0], {"rs2", "rs3", "rs4"})
		self.assertEqual(self.found('"karnataka sangeeta"')[0], {"rs3"})
		self.assertEqual(self.found("vachana -basavannanavara")[0], set())

	def test_switched_off(self):
		frappe.db.set_single_value("RD Settings", "search_romanised", 0)
		frappe.clear_document_cache("RD Settings", "RD Settings")
		self.assertEqual(self.found("vachana"), (set(), []))


class TestRequirements(OpsTestCase):
	def test_the_list_and_installing_from_the_desk(self):
		from sok_resdesk import requirements

		report = requirements.report(refresh=1)
		keys = {i["key"] for i in report["items"]}
		self.assertTrue(
			{"python", "frappe", "mariadb", "redis", "meilisearch", "tesseract", "boto3", "disk"} <= keys
		)
		python = next(i for i in report["items"] if i["key"] == "python")
		self.assertEqual(python["state"], "ok")
		if report["mode"] == "docker":
			# every upgrade brings OCR with the image: Tesseract reads Kannada in it
			from sok_resdesk.core import ocr_engine

			self.assertIn("kan", ocr_engine.available())
			self.assertEqual(next(i for i in report["items"] if i["key"] == "tesseract")["state"], "ok")
		self.assertTrue(all(i["state"] in ("ok", "missing", "old", "warn", "off") for i in report["items"]))
		self.assertIn(requirements.health_check()["state"], ("ok", "warn", "bad"))
		# installing: only the known parts, only on native installs, through the helper
		self.assertRaises(frappe.ValidationError, requirements.install, "curl evil | sh")
		with mock.patch("sok_resdesk.requirements.install_mode", return_value="docker"):
			self.assertRaises(frappe.ValidationError, requirements.install, "ocr")
		with (
			mock.patch("sok_resdesk.requirements.install_mode", return_value="native"),
			mock.patch("sok_resdesk.server.helper_configured", return_value=True),
			mock.patch("sok_resdesk.server.helper_connected", return_value=True),
			mock.patch("sok_resdesk.server.desk_control_allowed", return_value=True),
		):
			name = requirements.install("ocr")
		task = frappe.get_doc("RD Server Task", name)
		self.assertEqual(
			(task.action, frappe.parse_json(task.args)), ("install_requirements", {"part": "ocr"})
		)
		frappe.delete_doc("RD Server Task", name, force=True, ignore_permissions=True)


class TestOcrLanguages(OpsTestCase):
	def test_book_languages_and_the_choice_per_run(self):
		from sok_resdesk import reocr

		book = _item(97)
		# a book catalogued in several languages ("mul") is read in each, not in English only
		frappe.db.set_value("RD Item", book, {"language": "mul", "language_label": "Kannada; Sanskrit"})
		self.assertEqual(reocr.book_languages(book), ["kan", "san", "eng"])
		# OCR Languages on the form win, in their order
		frappe.db.set_value("RD Item", book, "ocr_languages", "Sanskrit, Kannada")
		self.assertEqual(reocr.book_languages(book), ["san", "kan", "eng"])
		with mock.patch("sok_resdesk.core.ocr_engine.available", return_value=["kan", "san", "eng"]):
			self.assertEqual(reocr.models_for(book), "san+kan+eng")
			self.assertEqual(reocr.models_for(book, ["kan", "san"]), "kan+san+eng")  # chosen for this run
			frappe.db.set_value("RD Item", book, "visibility", "Public")
			reocr.ocr_page(book, 1, None, '["kan", "san"]')
			method, kw = self.enqueued[-1]
			self.assertEqual((method, kw["languages"]), ("sok_resdesk.reocr.ocr_page_job", ["kan", "san"]))
			reocr.enqueue_book(book, "Whole page", '["san"]')
			self.assertEqual(self.enqueued[-1][1]["languages"], ["san"])


class TestEngineLoad(OpsTestCase):
	"""0.38.1: the search engine is asked to do only real work (the real engine, on test indexes)."""

	def setUp(self):
		super().setUp()
		from sok_resdesk import search

		real = search.MeiliClient.from_settings()
		self.client = search.MeiliClient(
			real.url, real.session.headers.get("Authorization", "")[7:], "rdtestload"
		)
		self.drop()
		p = mock.patch("sok_resdesk.search.MeiliClient.from_settings", return_value=self.client)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(self.drop)
		# the settings changed here are rolled back after the test: so must the cached copy be
		self.addCleanup(frappe.clear_document_cache, "RD Settings", "RD Settings")

	def drop(self):
		for index in (self.client.books, self.client.pages):
			try:
				self.client.wait(self.client._req("DELETE", f"/indexes/{index}"), timeout=60)
			except Exception:
				pass
			frappe.cache.delete_value(f"resdesk:meili-settings:{self.client.url}:{index}")

	def tasks(self, index, **params):
		return self.client._req("GET", "/tasks", params={"indexUids": index, "limit": 1, **params})["total"]

	def settle(self):
		last = self.client._req("GET", "/tasks", params={"limit": 1})["results"][0]
		self.client.wait({"taskUid": last["uid"]}, timeout=120)

	def test_settings_are_sent_once(self):
		from sok_resdesk import search

		before = self.tasks(self.client.pages, types="settingsUpdate")  # earlier runs' indexes of this name
		self.client.setup()
		sent = self.tasks(self.client.pages, types="settingsUpdate")
		self.assertEqual(sent, before + 1)
		self.client.setup()  # remembered: nothing asked or sent
		# forgotten (another worker, a restart): asked, found the same, still nothing sent
		frappe.cache.delete_value(f"resdesk:meili-settings:{self.client.url}:{self.client.pages}")
		self.client.setup()
		self.assertEqual(self.tasks(self.client.pages, types="settingsUpdate"), sent)
		self.assertEqual(
			search.settings_diff(
				search.PAGE_SETTINGS, self.client._req("GET", f"/indexes/{self.client.pages}/settings")
			),
			{},
		)
		# a setting that differs is sent on its own
		self.assertEqual(
			search.settings_diff(
				{"searchCutoffMs": 900, "sortableAttributes": ["leaf"]},
				{"searchCutoffMs": 1500, "sortableAttributes": ["leaf"]},
			),
			{"searchCutoffMs": 900},
		)

	def test_edits_that_change_nothing_send_nothing(self):
		from sok_resdesk import search
		from sok_resdesk.catalogue import item_to_record

		self.client.setup()
		name = _item(1)
		frappe.db.set_single_value("RD Settings", {"index_pages": 1, "hold_page_text": 0})
		frappe.clear_document_cache("RD Settings", "RD Settings")
		pages = [{"leaf": i, "label": "", "text": f"page {i} text"} for i in range(3)]
		search.index_record(item_to_record(frappe.get_doc("RD Item", name)), pages, self.client)
		self.settle()
		self.assertTrue(frappe.db.get_value("RD Item", name, "page_text_hash"))
		books, page_tasks = self.tasks(self.client.books), self.tasks(self.client.pages)

		search.update_item_fields([name], self.client, wait=True)  # saved, nothing the engine keeps changed
		self.assertEqual((self.tasks(self.client.books), self.tasks(self.client.pages)), (books, page_tasks))

		frappe.db.set_value("RD Item", name, "year", 1951)  # a field the pages carry
		search.update_item_fields([name], self.client, wait=True)
		self.assertEqual(self.tasks(self.client.books), books + 1)
		self.assertEqual(self.tasks(self.client.pages), page_tasks + 1)
		hit = self.client.search(self.client.pages, {"q": "", "filter": "year = 1951", "limit": 5})
		self.assertEqual(len(hit["hits"]), 3)

	def test_same_page_text_is_not_sent_again(self):
		from sok_resdesk import search
		from sok_resdesk.catalogue import item_to_record

		self.client.setup()
		name = _item(2)
		frappe.db.set_single_value("RD Settings", {"index_pages": 1, "hold_page_text": 0})
		frappe.clear_document_cache("RD Settings", "RD Settings")
		pages = [{"leaf": i, "label": "", "text": f"page {i} text"} for i in range(3)]
		buf = search.IndexBuffer(self.client)
		buf.add(item_to_record(frappe.get_doc("RD Item", name)), pages, replace_pages=False)
		buf.flush()
		self.settle()
		page_tasks = self.tasks(self.client.pages)
		deletions = self.tasks(self.client.pages, types="documentDeletion")

		# fetched again with the same text and a new year: the pages only get the year
		frappe.db.set_value("RD Item", name, "year", 1952)
		buf.add(item_to_record(frappe.get_doc("RD Item", name)), pages, if_changed=True)
		buf.flush()
		self.settle()
		self.assertEqual(self.tasks(self.client.pages), page_tasks + 1)  # one field update, no delete
		self.assertEqual(self.tasks(self.client.pages, types="documentDeletion"), deletions)
		hit = self.client.search(self.client.pages, {"q": "", "filter": "year = 1952", "limit": 5})
		self.assertEqual(len(hit["hits"]), 3)

		# different text: sent again, the old pages first taken out
		pages[1]["text"] = "corrected"
		buf.add(item_to_record(frappe.get_doc("RD Item", name)), pages, if_changed=True)
		buf.flush()
		self.settle()
		self.assertEqual(self.tasks(self.client.pages, types="documentDeletion"), deletions + 1)
		self.assertEqual(self.client.search(self.client.pages, {"q": "corrected"})["hits"][0]["leaf"], 1)
