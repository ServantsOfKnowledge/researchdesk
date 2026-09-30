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
