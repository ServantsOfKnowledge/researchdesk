"""0.81: retention rules, legal holds and disposal."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import retention


class TestRetention(IntegrationTestCase):
	DEPT = "RD Test Retention"

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.cache.delete_value("RD Settings")
		frappe.get_doc({"doctype": "RD Department", "department_name": self.DEPT}).insert(
			ignore_permissions=True
		)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		# disposals and holds are never deleted by the product, so the test clears them directly
		frappe.db.delete("RD Disposal Item", {"item": ("like", "rdretest%")})
		frappe.db.delete("RD Disposal", {"rule": ("like", "rdretest%")})
		frappe.db.delete("RD Legal Hold Item", {"item": ("like", "rdretest%")})
		frappe.db.delete("RD Legal Hold", {"hold_name": ("like", "rdretest%")})
		for name in frappe.get_all(
			"RD Retention Rule", filters={"rule_name": ("like", "rdretest%")}, pluck="name"
		):
			frappe.delete_doc("RD Retention Rule", name, force=True, ignore_permissions=True)
		frappe.db.delete("RD Item Scope", {"item": ("like", "rdretest%")})
		frappe.db.delete("RD Item", {"name": ("like", "rdretest%")})
		frappe.db.delete("RD Department", {"name": self.DEPT})
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.db.commit()

	def item(self, n, year=1990):
		doc = frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": f"rdretest{n}",
				"title": f"Ret {n}",
				"visibility": "Public",
				"year": year,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "RD Item Scope",
				"item": doc.name,
				"classification": "Restricted",
				"department": self.DEPT,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def rule(self, name="rdretest-rule", years=10, action="Destroy"):
		return frappe.get_doc(
			{
				"doctype": "RD Retention Rule",
				"rule_name": name,
				"years": years,
				"basis": "Year of the record",
				"action": action,
				"department": self.DEPT,
			}
		).insert(ignore_permissions=True)

	def hold(self, **values):
		return frappe.get_doc(
			{"doctype": "RD Legal Hold", "hold_name": "rdretest-hold", "reference": "Order 1/2026", **values}
		).insert(ignore_permissions=True)

	def test_a_held_record_cannot_be_deleted_until_the_hold_is_released(self):
		a = self.item(1)
		h = self.hold(items=[{"item": a}])
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("RD Item", a, force=True, ignore_permissions=True)
		h.status = "Released"
		h.save(ignore_permissions=True)
		frappe.delete_doc("RD Item", a, force=True, ignore_permissions=True)
		assert not frappe.db.exists("RD Item", a)

	def test_a_department_hold_covers_its_records(self):
		a = self.item(2)
		self.hold(department=self.DEPT)
		assert retention.held([a]) == {a}

	def test_a_hold_needs_records_or_a_department(self):
		with self.assertRaises(frappe.ValidationError):
			self.hold()

	def test_a_due_record_is_listed_and_disposed_only_after_approval(self):
		a = self.item(3)
		self.rule()
		assert retention.prepare() == 1
		d = frappe.get_doc("RD Disposal", {"rule": "rdretest-rule"})
		assert [r.item for r in d.items] == [a]
		assert frappe.db.exists("RD Item", a)  # listing disposes of nothing
		retention.approve(d.name)
		retention.execute(d.name)
		assert not frappe.db.exists("RD Item", a)
		assert frappe.db.get_value("RD Disposal", d.name, "status") == "Done"

	def test_a_record_not_yet_due_is_not_listed(self):
		self.item(4, year=2999)
		self.rule()
		assert retention.prepare() == 0

	def test_a_hold_placed_after_the_list_wins(self):
		a = self.item(5)
		self.rule()
		retention.prepare()
		d = frappe.get_doc("RD Disposal", {"rule": "rdretest-rule"})
		self.hold(items=[{"item": a}])
		retention.approve(d.name)
		retention.execute(d.name)
		assert frappe.db.exists("RD Item", a)
		assert frappe.get_doc("RD Disposal", d.name).items[0].why == "legal hold"

	def test_the_longest_rule_governs(self):
		self.item(6)
		self.rule("rdretest-short", 10)
		self.rule("rdretest-long", 2000)
		assert retention.prepare() == 0

	def test_a_held_records_department_cannot_be_changed_under_it(self):
		a = self.item(7)
		self.hold(items=[{"item": a}])
		other = frappe.get_doc({"doctype": "RD Department", "department_name": "RD Test Retention 2"}).insert(
			ignore_permissions=True
		)
		self.addCleanup(lambda: frappe.db.delete("RD Department", {"name": other.name}))
		scope = frappe.get_doc("RD Item Scope", a)
		scope.department = other.name
		with self.assertRaises(frappe.ValidationError):
			scope.save(ignore_permissions=True)

	def test_a_disposal_cannot_be_made_or_changed_by_hand(self):
		self.item(8)
		self.rule()
		frappe.flags.rd_retention = False
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "RD Disposal", "rule": "rdretest-rule", "items": []}).insert(
				ignore_permissions=True
			)

	def test_only_a_draft_can_be_cancelled(self):
		self.item(9)
		self.rule()
		retention.prepare()
		d = frappe.get_doc("RD Disposal", {"rule": "rdretest-rule"}).name
		retention.approve(d)
		with self.assertRaises(frappe.ValidationError):
			retention.cancel(d)

	def test_a_hold_is_released_never_deleted(self):
		h = self.hold(items=[{"item": self.item(10)}])
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("RD Legal Hold", h.name, force=True, ignore_permissions=True)
