"""Integration tests for trying failed ingest work again (jobs.retry_run). Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_retry
"""

import json
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import jobs

PROFILE = "Retry test profile"


class TestRetry(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("RD Ingest Profile", PROFILE):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": PROFILE,
					"source": "Internet Archive",
					"scope_type": "Identifier List",
					"identifiers": "a\nb",
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		# one active run per profile: runs left going by other tests would be in the way
		frappe.db.delete(
			"RD Ingest Run", {"profile": PROFILE, "status": ("in", ["Queued", "Running", "Paused"])}
		)

	def make_run(self, **values):
		run = frappe.get_doc(
			{"doctype": "RD Ingest Run", "profile": PROFILE, "status": "Completed", **values}
		)
		run.insert(ignore_permissions=True)
		return run

	def test_failed_books_are_read_from_the_run_or_its_log(self):
		run = self.make_run(
			failed_items=json.dumps("x1") + "\n" + json.dumps(["x2", "/library-source/x2"]) + "\n"
		)
		self.assertEqual(jobs._failed_books(run), ["x1", ["x2", "/library-source/x2"]])
		old = self.make_run(
			log="10:00:00 FAIL old-1: boom\n10:00:01 something else\n10:00:02 FAIL old-2: dark\n"
		)
		self.assertEqual(jobs._failed_books(old), ["old-1", "old-2"])

	@mock.patch("sok_resdesk.jobs._failed_registry_jobs", return_value=[])
	@mock.patch("frappe.enqueue")
	def test_retry_takes_the_failed_books_again_in_the_same_run(self, enqueue, _registry):
		run = self.make_run(
			status="Completed with Errors",
			processed=10,
			failed_count=3,
			chunks_total=2,
			failed_items="".join(json.dumps(f"b{i}") + "\n" for i in range(3)),
		)
		result = jobs.retry_run(run.name)
		self.assertEqual(result["books"], 3)
		row = frappe.db.get_value(
			"RD Ingest Run",
			run.name,
			["status", "processed", "failed_count", "pending_chunks", "chunks_total", "failed_items"],
			as_dict=True,
		)
		self.assertEqual((row.status, row.processed, row.failed_count), ("Running", 7, 0))
		self.assertEqual((row.pending_chunks, row.chunks_total), (1, 3))
		self.assertFalse(row.failed_items)
		kwargs = enqueue.call_args.kwargs
		self.assertEqual((kwargs["item_ids"], kwargs["batch_no"]), (["b0", "b1", "b2"], 3))

	@mock.patch("sok_resdesk.jobs._failed_registry_jobs", return_value=[])
	@mock.patch("sok_resdesk.ingest.enqueue_plan")
	def test_failed_or_interrupted_runs_list_their_books_again(self, enqueue_plan, _registry):
		for status in ("Failed", "Interrupted"):
			run = self.make_run(status=status, failed_count=2)
			jobs.retry_run(run.name)
			self.assertEqual(
				frappe.db.get_value("RD Ingest Run", run.name, ["status", "failed_count"]), ("Queued", 0)
			)
			enqueue_plan.assert_called_with(run.name)
			frappe.db.delete("RD Ingest Run", run.name)  # one active run per profile

	def test_running_runs_are_left_alone(self):
		run = self.make_run(status="Running")
		self.assertRaises(frappe.ValidationError, jobs.retry_run, run.name)

	def test_failed_jobs_are_found_under_frappes_queue_names(self):
		# the Server page's list used the bare queue names and so never found a failed job
		from frappe.utils.background_jobs import get_queues, get_redis_conn

		names = [q.name for q in get_queues(connection=get_redis_conn())]
		self.assertTrue(names)
		self.assertTrue(all(":" in n for n in names), names)  # e.g. home-frappe-frappe-bench:long
		self.assertIsInstance(jobs._failed_registry_jobs(), list)
