"""Books already ingested aren't fetched again, runs that lose their workers carry on by
themselves, and books left out at the book limit come in with Carry On. Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_no_double_work
"""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from sok_resdesk import ingest, jobs

PROFILE = "No double work profile"
RUN = "tabRD Ingest Run"


class TestNoDoubleWork(IntegrationTestCase):
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
					"update_existing": 1,
				}
			).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		# run_batch commits, so take out what these tests added (the book limit tests count books),
		# from the search index too: a book left there leads to a page that doesn't exist
		from sok_resdesk.search import remove_record

		for name in frappe.get_all("RD Item", filters={"name": ("like", "ndw-%")}, pluck="name"):
			try:
				remove_record(name)
			except Exception:
				pass
		frappe.db.delete("RD Item", {"name": ("like", "ndw-%")})
		frappe.db.delete("RD Ingest Run", {"profile": PROFILE})
		frappe.db.commit()
		super().tearDownClass()

	def make_run(self, **values):
		run = frappe.get_doc({"doctype": "RD Ingest Run", "profile": PROFILE, "status": "Running", **values})
		run.insert(ignore_permissions=True)
		return run

	def make_item(self, item_id, last_ingested):
		if not frappe.db.exists("RD Item", item_id):
			frappe.get_doc(
				{"doctype": "RD Item", "item_id": item_id, "title": item_id, "source": "Internet Archive"}
			).insert(ignore_permissions=True)
		frappe.db.set_value("RD Item", item_id, "last_ingested", last_ingested, update_modified=False)

	def test_books_done_since_the_run_started_are_not_fetched_again(self):
		started = add_to_date(now_datetime(), hours=-1)
		self.make_item("ndw-done", now_datetime())  # done by another run (or this one) meanwhile
		self.make_item("ndw-old", add_to_date(now_datetime(), days=-3))  # in the catalogue from before
		self.assertTrue(ingest._already_done("ndw-done", started, only_new=False))
		self.assertFalse(ingest._already_done("ndw-old", started, only_new=False))
		self.assertTrue(ingest._already_done("ndw-old", started, only_new=True))
		self.assertFalse(ingest._already_done("ndw-missing", started, only_new=True))
		self.assertEqual(ingest._done_since(["ndw-done", "ndw-old", "ndw-missing"], started), {"ndw-done"})

	@mock.patch("sok_resdesk.ingest._ingest_one", return_value=(False, 0))
	def test_a_batch_skips_books_another_run_has_done(self, ingest_one):
		run = self.make_run(
			started_on=add_to_date(now_datetime(), hours=-1), pending_chunks=1, chunks_total=1
		)
		self.make_item("ndw-b1", now_datetime())
		self.make_item("ndw-b2", add_to_date(now_datetime(), days=-3))
		ingest.run_batch(run.name, ["ndw-b1", "ndw-b2"], 1)
		# update_existing is on, so the older book is refreshed; the one done meanwhile is not
		self.assertEqual([c.args[1] for c in ingest_one.call_args_list], ["ndw-b2"])
		row = frappe.db.get_value(
			"RD Ingest Run", run.name, ["processed", "skipped_count", "updated_count", "log"], as_dict=True
		)
		self.assertEqual((row.processed, row.skipped_count, row.updated_count), (2, 1, 1))
		self.assertIn("1 books already done by another run", row.log)

	@mock.patch("sok_resdesk.ingest._ingest_one")
	@mock.patch("sok_resdesk.capacity.has_room", return_value=False)
	def test_books_left_out_at_the_book_limit_are_counted_and_carried_on(self, _room, ingest_one):
		run = self.make_run(started_on=now_datetime(), pending_chunks=1, chunks_total=1)
		ingest.run_batch(run.name, ["ndw-new-1", "ndw-new-2"], 1)
		ingest_one.assert_not_called()
		row = frappe.db.get_value("RD Ingest Run", run.name, ["status", "limit_skipped", "log"], as_dict=True)
		self.assertEqual((row.status, row.limit_skipped), ("Completed", 2))
		self.assertIn("BOOK LIMIT: 2 new books were left out", row.log)
		with mock.patch("sok_resdesk.jobs._failed_registry_jobs", return_value=[]):
			self.assertRaises(frappe.ValidationError, jobs.retry_run, run.name)  # still full
			_room.return_value = True
			with mock.patch("sok_resdesk.ingest.enqueue_plan") as enqueue_plan:
				jobs.retry_run(run.name)
		enqueue_plan.assert_called_with(run.name)
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run.name, "status"), "Queued")

	@mock.patch("sok_resdesk.jobs.retry_run")
	@mock.patch("sok_resdesk.holding.is_paused", return_value=False)
	def test_runs_whose_batches_vanished_are_interrupted_and_carried_on(self, _paused, retry_run):
		old = add_to_date(now_datetime(), minutes=-30)
		lost = self.make_run(started_on=old)
		alive = self.make_run(started_on=old)
		fresh = self.make_run(started_on=now_datetime())
		frappe.db.sql(f"update `{RUN}` set modified=%s where name in (%s, %s)", (old, lost.name, alive.name))
		with mock.patch("sok_resdesk.ingest._runs_with_work", return_value={alive.name}):
			ingest.mark_interrupted_runs()
		status = lambda r: frappe.db.get_value("RD Ingest Run", r.name, "status")  # noqa: E731
		self.assertEqual(status(lost), "Interrupted")
		self.assertEqual((status(alive), status(fresh)), ("Running", "Running"))
		carried = [c.args[0] for c in retry_run.call_args_list]
		self.assertIn(lost.name, carried)
		self.assertNotIn(alive.name, carried)
		self.assertNotIn(fresh.name, carried)
		self.assertIn("Carried on by itself", frappe.db.get_value("RD Ingest Run", lost.name, "log"))

		# not forever: after AUTO_CARRY_ON tries it stays Interrupted for someone to look at
		retry_run.reset_mock()
		frappe.db.sql(
			f"update `{RUN}` set status='Running', modified=%s, log=%s where name=%s",
			(old, "Carried on by itself\n" * ingest.AUTO_CARRY_ON, lost.name),
		)
		with mock.patch("sok_resdesk.ingest._runs_with_work", return_value={alive.name}):
			ingest.mark_interrupted_runs()
		self.assertEqual(status(lost), "Interrupted")
		self.assertNotIn(lost.name, [c.args[0] for c in retry_run.call_args_list])

	@mock.patch("sok_resdesk.holding.is_paused", return_value=False)
	def test_nothing_is_decided_when_the_queue_cant_be_read(self, _paused):
		old = add_to_date(now_datetime(), minutes=-30)
		run = self.make_run(started_on=old)
		frappe.db.sql(f"update `{RUN}` set modified=%s where name=%s", (old, run.name))
		with mock.patch("sok_resdesk.ingest._runs_with_work", side_effect=ConnectionError("redis down")):
			ingest.mark_interrupted_runs()
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run.name, "status"), "Running")

	def test_the_queue_can_be_read(self):
		self.assertIsInstance(ingest._runs_with_work(), set)


class FakeIA:
	def __init__(self, ids):
		self.ids = ids

	def count(self, query):
		return len(self.ids)

	def iter_identifiers(self, query, limit=0):
		yield from self.ids


@mock.patch("sok_resdesk.ingest._window", return_value=4)
@mock.patch("sok_resdesk.search.MeiliClient")
class TestFeeding(IntegrationTestCase):
	"""Batches go into the queue a few at a time, so a big run neither fills the queue nor
	holds up everything else."""

	profile = "Feeding test search profile"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("RD Ingest Profile", cls.profile):
			frappe.get_doc(
				{
					"doctype": "RD Ingest Profile",
					"profile_name": cls.profile,
					"source": "Internet Archive",
					# a search, so the (stand-in) archive.org lists the books: a list is taken as is
					"scope_type": "Search Query",
					"ia_query": "collection:feeding-test",
				}
			).insert(ignore_permissions=True)
		cls.batch_size = frappe.db.get_single_value("RD Settings", "batch_size")
		frappe.db.set_single_value("RD Settings", "batch_size", 2)

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value("RD Settings", "batch_size", cls.batch_size)
		frappe.db.delete("RD Ingest Run", {"profile": cls.profile})
		frappe.db.commit()
		super().tearDownClass()

	def planned_run(self, enqueue, n=20):
		frappe.db.delete("RD Ingest Run", {"profile": self.profile})
		run = ingest.create_run(frappe.get_doc("RD Ingest Profile", self.profile))
		with mock.patch("sok_resdesk.ingest.client", return_value=FakeIA([f"feed-{i}" for i in range(n)])):
			ingest.plan_run(run.name)
		return run.name

	@mock.patch("frappe.enqueue")
	def test_a_big_run_queues_a_few_batches_at_a_time(self, enqueue, _meili, _window):
		run = self.planned_run(enqueue)
		self.assertEqual(enqueue.call_count, 4)
		self.assertEqual([c.kwargs["batch_no"] for c in enqueue.call_args_list], [1, 2, 3, 4])
		self.assertEqual(len(ingest.waiting_batches(run)), 6)
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "pending_chunks"), 10)
		# a batch finishing lets the next one in
		ingest._close_batch(run)
		self.assertEqual(enqueue.call_args.kwargs["batch_no"], 5)
		self.assertEqual(len(ingest.waiting_batches(run)), 5)
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "pending_chunks"), 9)

	@mock.patch("frappe.enqueue")
	def test_a_second_run_of_the_same_profile_is_refused(self, enqueue, _meili, _window):
		self.planned_run(enqueue)
		self.assertRaises(
			frappe.ValidationError, ingest.create_run, frappe.get_doc("RD Ingest Profile", self.profile)
		)

	@mock.patch("sok_resdesk.jobs._rq_jobs", return_value=[])
	@mock.patch("frappe.enqueue")
	def test_pause_keeps_the_waiting_batches_and_resume_feeds_them(self, enqueue, _jobs, _meili, _window):
		run = self.planned_run(enqueue)
		jobs._pause_ingest(run, "Administrator")
		row = frappe.db.get_value(
			"RD Ingest Run", run, ["status", "held_work", "pending_chunks"], as_dict=True
		)
		self.assertEqual(row.status, "Paused")
		self.assertEqual(len(frappe.parse_json(row.held_work)["items"]), 12)  # 6 waiting batches of 2
		self.assertEqual(row.pending_chunks, 4)  # the 4 already in the queue
		self.assertEqual(ingest.waiting_batches(run), [])
		enqueue.reset_mock()
		jobs._resume_ingest(run, "Administrator")
		self.assertEqual(enqueue.call_count, 4)
		self.assertEqual(len(ingest.waiting_batches(run)), 2)
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "pending_chunks"), 10)
		self.assertEqual(len({c.kwargs["job_id"] for c in enqueue.call_args_list}), 4)

	@mock.patch("sok_resdesk.jobs.retry_run")
	@mock.patch("sok_resdesk.holding.is_paused", return_value=False)
	@mock.patch("frappe.enqueue")
	def test_waiting_batches_are_queued_rather_than_the_run_interrupted(
		self, enqueue, _paused, retry_run, _meili, _window
	):
		run = self.planned_run(enqueue, n=8)  # 4 batches: all queued at once
		# pretend the queued ones finished and the rest never got in
		frappe.db.sql(
			f"update `{RUN}` set pending_chunks=2, modified=%s, waiting_work=%s where name=%s",
			(add_to_date(now_datetime(), minutes=-30), '{"batches": [["x"], ["y"]], "next_no": 5}', run),
		)
		enqueue.reset_mock()
		with mock.patch("sok_resdesk.ingest._runs_with_work", return_value=set()):
			ingest.mark_interrupted_runs()
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "status"), "Running")
		self.assertEqual(enqueue.call_count, 2)
		self.assertNotIn(run, [c.args[0] for c in retry_run.call_args_list])

	@mock.patch("frappe.enqueue", side_effect=Exception("Too many queued background jobs (550)"))
	def test_a_full_queue_leaves_the_batches_waiting(self, enqueue, _meili, _window):
		run = self.planned_run(enqueue)
		self.assertEqual(frappe.db.get_value("RD Ingest Run", run, "status"), "Running")
		self.assertEqual(len(ingest.waiting_batches(run)), 10)
		self.assertIn("queue busy", frappe.db.get_value("RD Ingest Run", run, "log"))
