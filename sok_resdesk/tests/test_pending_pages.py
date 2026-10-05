"""0.46.1: why page text waiting to be sent is not moving, and sending it now."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import search_queue


class TestPendingPages(IntegrationTestCase):
	def setUp(self):
		self.was = {
			k: frappe.db.get_single_value("RD Settings", k)
			for k in ("hold_page_text", "pause_background", "index_pages")
		}
		frappe.get_doc(
			{"doctype": "RD Item", "item_id": "rdtestpend1", "title": "Pending pages", "pages_pending": 1}
		).insert(ignore_permissions=True)
		self.addCleanup(self._clean)
		self.set(hold_page_text=0, pause_background=0, index_pages=1)

	def _clean(self):
		for k, v in self.was.items():
			frappe.db.set_single_value("RD Settings", k, v or 0)
		frappe.db.delete("RD Item", {"name": ("like", "rdtestpend%")})
		frappe.db.commit()

	def set(self, **values):
		for k, v in values.items():
			frappe.db.set_single_value("RD Settings", k, v)

	def why(self, waiting=0, rate=1.0):
		with mock.patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=False):
			return (search_queue.pending_why(waiting, rate) or {}).get("code")

	def test_the_reasons(self):
		self.set(hold_page_text=1)
		self.assertEqual(self.why(), "held")
		self.set(hold_page_text=0, pause_background=1)
		self.assertEqual(self.why(), "paused")
		self.set(pause_background=0)
		with mock.patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=True):
			self.assertEqual((search_queue.pending_why(0, 1) or {}).get("code"), "scheduler")
		self.set(index_pages=0)
		self.assertEqual(self.why(), "off")
		self.set(index_pages=1)
		self.assertEqual(self.why(waiting=search_queue.MAX_WAITING // 2 + 1), "busy")
		self.assertEqual(self.why(waiting=50, rate=0), "stalled")
		self.assertEqual(self.why(waiting=50, rate=2), "waiting")
		frappe.db.set_value("RD Item", "rdtestpend1", "pages_pending", 0)
		self.assertIsNone(search_queue.pending_why(50, 2))  # nothing waits: no reason needed

	def test_send_now_queues_the_sender_unless_held(self):
		with mock.patch("sok_resdesk.search_queue._queue_send") as queue:
			self.assertTrue(search_queue.send_now()["queued"])
			queue.assert_called_once()
			self.set(hold_page_text=1)
			with self.assertRaises(frappe.ValidationError):
				search_queue.send_now()
			self.assertEqual(queue.call_count, 1)
