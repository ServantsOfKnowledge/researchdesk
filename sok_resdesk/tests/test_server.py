"""Integration tests for the Server page: the updater helper's protocol, tasks and who may start
them, update checks, health, alerts, backups and logs. Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_server
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from sok_resdesk import server

TOKEN = "t" * 64
MANAGER = "rdtest.server.manager@example.org"
CHANGELOG = """# Changelog

## 99.1.0 (2099-01-01): far future

- Something new

## 0.1.0 (2026-01-01): old
"""


class ServerTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# what the site knew about releases before these tests, put back afterwards
		cls._defaults = {k: frappe.db.get_default(k) for k in ("resdesk_updates", "resdesk_update_notified")}

	@classmethod
	def tearDownClass(cls):
		for k, v in cls._defaults.items():
			frappe.db.set_default(k, v or "")
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._conf = mock.patch.dict(frappe.local.conf, {"resdesk_agent_token": TOKEN})
		self._conf.start()
		self.addCleanup(self._conf.stop)
		self._saved = frappe.db.get_singles_dict("RD Settings")
		frappe.cache.delete_value(server.AGENT_CACHE)
		self._tasks = set(frappe.get_all(server.TASK, pluck="name"))
		# tasks from before the test (a real site's history) wait aside, so they don't count
		frappe.db.sql(
			f"update `tab{server.TASK}` set status='Cancelled' where status in ('Queued','Running')"
		)
		self.alerts = []
		self.real_send_alert = server.send_alert
		p = mock.patch.object(server, "send_alert", side_effect=lambda *a, **k: self.alerts.append(a))
		p.start()
		self.addCleanup(p.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in set(frappe.get_all(server.TASK, pluck="name")) - self._tasks:
			frappe.db.delete(server.TASK, name)
		for f in ("allow_desk_upgrades", "alert_webhook_url", "alert_email"):
			frappe.db.set_single_value("RD Settings", f, self._saved.get(f))
		frappe.cache.delete_value(server.AGENT_CACHE)
		frappe.db.commit()

	def sync(self, facts=None, job=None, token=TOKEN):
		frappe.set_user("Guest")
		try:
			return server.agent_sync(
				token=token,
				facts=json.dumps(facts or {"version": "0.11.0", "mode": "docker"}),
				job=json.dumps(job) if job else None,
			)
		finally:
			frappe.set_user("Administrator")

	def manager(self):
		if not frappe.db.exists("User", MANAGER):
			user = frappe.get_doc(
				{"doctype": "User", "email": MANAGER, "first_name": "Manager", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("ResDesk Manager")
		return MANAGER


class TestHelperProtocol(ServerTestCase):
	def test_token_is_required(self):
		self.assertRaises(frappe.PermissionError, self.sync, token="")
		self.assertRaises(frappe.PermissionError, self.sync, token="wrong")
		with mock.patch.dict(frappe.local.conf, {"resdesk_agent_token": ""}):
			self.assertRaises(frappe.PermissionError, self.sync, token="")
		self.assertFalse(server.helper_connected())
		self.assertEqual(self.sync(), {"task": None, "allowed": True, "send_releases": True})
		self.sync({"version": "0.11.0", "tags": ["v0.11.0"]})
		self.assertFalse(self.sync()["send_releases"])  # remembered between syncs
		self.assertTrue(server.helper_connected())
		self.assertEqual(server.agent_facts()["mode"], "docker")

	def test_task_round_trip(self):
		self.assertRaises(
			frappe.ValidationError, server.request_task, "restart", json.dumps({"service": "web"})
		)
		self.sync()  # the helper is now connected
		name = server.request_task("restart", json.dumps({"service": "web"}))
		self.assertEqual(frappe.db.get_value(server.TASK, name, "status"), "Queued")
		# one change to the installation at a time
		self.assertRaises(frappe.ValidationError, server.request_task, "upgrade", "{}")
		answer = self.sync()
		self.assertEqual(answer["task"], {"name": name, "action": "restart", "args": {"service": "web"}})
		self.assertEqual(frappe.db.get_value(server.TASK, name, "status"), "Running")
		self.assertIsNone(self.sync()["task"])  # handed out once
		self.sync(job={"task": name, "status": "running", "log": "restarting…"})
		self.assertEqual(frappe.db.get_value(server.TASK, name, "log"), "restarting…")
		self.sync(
			job={"task": name, "status": "succeeded", "exit_code": 0, "log": "done", "summary": "Done."}
		)
		t = frappe.get_doc(server.TASK, name)
		self.assertEqual((t.status, t.exit_code, t.summary), ("Succeeded", 0, "Done."))
		self.assertTrue(t.finished_on)

	def test_upgrade_result_alerts_managers(self):
		self.sync()
		name = server.request_task("upgrade", json.dumps({"target": "latest"}))
		self.sync()
		self.sync(job={"task": name, "status": "failed", "exit_code": 1, "log": "boom", "summary": "boom"})
		self.assertEqual(self.alerts[-1][0], "upgrade_failed")

	def test_arguments_are_checked(self):
		self.sync()
		for action, args in (
			("upgrade", {"target": "v1.0.0; reboot"}),
			("restart", {"service": "db"}),
			("apply_resources", {"preset": "huge"}),
			("logs", {"service": "/etc/passwd"}),
			("shell", {}),
		):
			self.assertRaises(frappe.ValidationError, server.request_task, action, json.dumps(args))
		name = server.request_task("upgrade", json.dumps({"target": "0.11.0", "backup": 0, "frappe": 0}))
		self.assertEqual(
			json.loads(frappe.db.get_value(server.TASK, name, "args")),
			{"target": "v0.11.0", "backup": 0, "frappe": 0},
		)

	def test_managers_may_look_but_not_change(self):
		self.sync()
		frappe.set_user(self.manager())
		self.assertIn("health", server.status())
		self.assertTrue(server.request_task("logs", json.dumps({"service": "queue"})))
		self.assertRaises(frappe.PermissionError, server.request_task, "upgrade", "{}")
		self.assertRaises(
			frappe.PermissionError, server.request_task, "restart", json.dumps({"service": "all"})
		)
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, server.status)

	def test_desk_control_can_be_switched_off(self):
		self.sync()
		name = server.request_task("restart", json.dumps({"service": "workers"}))
		frappe.db.set_single_value("RD Settings", "allow_desk_upgrades", 0)
		self.assertRaises(frappe.ValidationError, server.request_task, "upgrade", "{}")
		self.assertIsNone(self.sync()["task"])  # a queued restart is cancelled, not run
		self.assertEqual(frappe.db.get_value(server.TASK, name, "status"), "Cancelled")
		self.assertTrue(server.request_task("logs", "{}"))  # looking is still fine


class TestUpdates(ServerTestCase):
	def test_check_updates_and_notes(self):
		def fake(url):
			if "matching-refs/tags/v16" in url:
				return [{"ref": "refs/tags/v16.35.0"}, {"ref": "refs/tags/v16.99.0"}]
			if "matching-refs" in url:
				return [{"ref": "refs/tags/v0.1.0"}, {"ref": "refs/tags/v99.1.0"}]
			return CHANGELOG

		with mock.patch.object(server, "_get_json", side_effect=fake):
			view = server.check_updates()
		self.assertEqual((view["latest"], view["newer"]), ("v99.1.0", True))
		self.assertEqual([n["version"] for n in view["notes"]], ["99.1.0"])
		self.assertEqual(view["frappe_latest"], "v16.99.0")
		self.assertTrue(view["frappe_newer"])
		self.assertEqual(self.alerts[-1][0], "update_available")
		n = len(self.alerts)
		with mock.patch.object(server, "_get_json", side_effect=fake):
			server.check_updates()
		self.assertEqual(len(self.alerts), n)  # told once per release

	def test_offline_check_keeps_working(self):
		with mock.patch.object(server, "_get_json", side_effect=OSError("no network")):
			view = server.check_updates()
		self.assertIn("no network", view["error"])
		self.assertFalse(view["newer"])

	def test_helper_knows_releases_too(self):
		frappe.db.set_default("resdesk_updates", "")
		self.sync({"version": "0.10.1", "tags": ["v0.10.1", "v99.1.0"], "changelog": CHANGELOG})
		view = server.updates_view()
		self.assertEqual((view["latest"], view["newer"]), ("v99.1.0", True))
		self.assertEqual(view["notes"][0]["title"], "far future")


class TestHealthAndAlerts(ServerTestCase):
	def test_health_lists_every_part(self):
		keys = [c["key"] for c in server.health()]
		for key in (
			"database",
			"cache",
			"workers",
			"scheduler",
			"search",
			"disk",
			"backups",
			"errors",
			"helper",
			"updates",
		):
			self.assertIn(key, keys)
		self.assertTrue(all(c["state"] in ("ok", "warn", "bad", "off", "info") for c in server.health()))

	def test_watch_alerts_on_change_only(self):
		frappe.db.set_default("resdesk_alert_state", "{}")
		state = [{"key": "search", "label": "Search engine", "state": "bad", "detail": "down"}]
		with mock.patch.object(server, "health", side_effect=lambda: state):
			server.watch()
			server.watch()
			self.assertEqual([a[0] for a in self.alerts], ["search"])
			state[0]["state"] = "ok"
			server.watch()
		self.assertEqual([a[1] for a in self.alerts], ["bad", "ok"])

	def test_alert_channels(self):
		frappe.db.set_single_value(
			"RD Settings", {"alert_webhook_url": "https://hooks.example.org/x", "alert_email": 0}
		)
		before = frappe.db.count("Notification Log", {"subject": ("like", "%test alert%")})
		with mock.patch("requests.post") as post:
			self.real_send_alert("test", "info", "This is a test alert")
		body = post.call_args.kwargs["json"]
		self.assertEqual((body["event"], body["severity"]), ("test", "info"))
		self.assertIn("This is a test alert", body["text"])
		self.assertGreater(frappe.db.count("Notification Log", {"subject": ("like", "%test alert%")}), before)
		frappe.db.delete("Notification Log", {"subject": ("like", "%test alert%")})

	def test_ping(self):
		frappe.set_user("Guest")
		self.assertIn(server.ping()["status"], ("ok", "degraded"))


class TestBackupsAndLogs(ServerTestCase):
	def test_list_and_trim_backups(self):
		site = frappe.local.site.replace(".", "_")
		with (
			tempfile.TemporaryDirectory() as d,
			mock.patch.object(server, "_backup_dir", return_value=Path(d)),
		):
			for n, stamp in enumerate(("20260101_010101", "20260102_010101", "20260103_010101")):
				for suffix in ("database.sql.gz", "files.tar", "private-files.tar"):
					p = Path(d) / f"{stamp}-{site}-{suffix}"
					p.write_bytes(b"x" * 10)
					os.utime(p, (time.time() - (3 - n) * 3600,) * 2)
			sets = server.list_backups()
			self.assertEqual(len(sets), 3)
			self.assertTrue(sets[0]["name"].startswith("20260103"))
			self.assertEqual([f["kind"] for f in sets[0]["files"]], ["database", "files", "private files"])
			self.assertEqual(server.trim_backups(2), 1)
			self.assertEqual([s["name"][:8] for s in server.list_backups()], ["20260103", "20260102"])
			server.delete_backup(sets[0]["name"])
			self.assertEqual(len(server.list_backups()), 1)

	def test_backup_job_records_result(self):
		with mock.patch("frappe.utils.backups.new_backup", side_effect=RuntimeError("disk full")):
			server.run_backup()
		last = json.loads(frappe.db.get_default("resdesk_last_backup"))
		self.assertFalse(last["ok"])
		self.assertEqual(self.alerts[-1][0], "backup_failed")
		check = server._backup_check(frappe.db.get_singles_dict("RD Settings"))
		self.assertEqual(check["state"], "bad")
		frappe.db.set_default("resdesk_last_backup", "")
		frappe.db.delete("Error Log", {"method": "Research Desk: backup failed"})
		frappe.db.commit()

	def test_logs(self):
		self.assertIn("rows", server.logs("errors"))
		self.assertIn("rows", server.logs("failed_jobs"))
		files = server.logs("files")["files"]
		if files:
			self.assertIsInstance(server.logs("files", files[0]["name"], 20)["text"], str)
		self.assertRaises(frappe.ValidationError, server.logs, "files", "../../sites/common_site_config.json")
		self.assertRaises(frappe.ValidationError, server.logs, "files", "no-such.log")

	def test_status_page(self):
		self.sync(
			{"version": "0.11.0", "mode": "docker", "services": [{"service": "backend", "state": "running"}]}
		)
		s = server.status()
		self.assertTrue(s["helper"]["connected"])
		self.assertEqual(s["helper"]["services"][0]["service"], "backend")
		self.assertTrue(s["is_admin"])
		self.assertTrue(str(now_datetime())[:4] in s["now"])
