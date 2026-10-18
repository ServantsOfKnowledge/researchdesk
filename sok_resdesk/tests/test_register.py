"""0.83: the file register."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import register


class TestRegister(IntegrationTestCase):
	DEPT = "RD Test Register"
	USERS = ("rdregtest-a@example.com", "rdregtest-b@example.com")

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.cache.delete_value("RD Settings")
		frappe.get_doc({"doctype": "RD Department", "department_name": self.DEPT}).insert(
			ignore_permissions=True
		)
		for u in self.USERS:
			frappe.get_doc(
				{
					"doctype": "User",
					"email": u,
					"first_name": "Reg",
					"send_welcome_email": 0,
					"roles": [{"role": "ResDesk Cataloguer"}],
				}
			).insert(ignore_permissions=True)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD File Movement", {"parent": ("like", "RDREGTEST%")})
		frappe.db.delete("RD File Record", {"parent": ("like", "RDREGTEST%")})
		frappe.db.delete("RD File", {"name": ("like", "RDREGTEST%")})
		frappe.db.delete("RD Item Scope", {"item": ("like", "rdregtest%")})
		frappe.db.delete("RD Item", {"name": ("like", "rdregtest%")})
		frappe.db.delete("RD Clearance Department", {"parent": ("in", self.USERS)})
		frappe.db.delete("RD Clearance", {"name": ("in", self.USERS)})
		for u in self.USERS:
			frappe.delete_doc("User", u, force=True, ignore_permissions=True)
		frappe.db.delete("RD Department", {"name": self.DEPT})
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.local.rd_clearance = {}
		frappe.db.commit()

	def file(self, number="RDREGTEST-1", **values):
		return frappe.get_doc(
			{"doctype": "RD File", "file_number": number, "subject": "A file", **values}
		).insert(ignore_permissions=True)

	def clear(self, user, level="Restricted"):
		frappe.local.rd_clearance = {}
		frappe.get_doc(
			{
				"doctype": "RD Clearance",
				"user": user,
				"level": level,
				"departments": [{"department": self.DEPT}],
			}
		).insert(ignore_permissions=True)

	def test_a_new_file_is_open_and_with_its_maker(self):
		f = self.file()
		assert (f.status, f.held_by) == ("Open", frappe.session.user)

	def test_a_file_without_a_number_is_numbered(self):
		f = frappe.get_doc({"doctype": "RD File", "subject": "No number"}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.delete("RD File", {"name": f.name}))
		assert f.name.startswith("F-")

	def test_a_file_is_sent_received_and_closed(self):
		a, b = self.USERS
		f = self.file(held_by=None)
		frappe.db.set_value("RD File", f.name, "held_by", a)
		frappe.set_user(a)
		register.send(f.name, b, "for action")
		with self.assertRaises(frappe.ValidationError):  # still on its way
			register.send(f.name, b)
		frappe.set_user(b)
		register.receive(f.name)
		doc = frappe.get_doc("RD File", f.name)
		assert doc.held_by == b and len(doc.movements) == 1 and doc.movements[0].received_on
		register.close(f.name)
		assert frappe.db.get_value("RD File", f.name, "status") == "Closed"

	def test_only_the_holder_can_send_and_only_the_addressee_can_receive(self):
		a, b = self.USERS
		f = self.file()
		frappe.db.set_value("RD File", f.name, "held_by", a)
		frappe.set_user(b)
		with self.assertRaises(frappe.PermissionError):
			register.send(f.name, a)
		frappe.set_user(a)
		register.send(f.name, b)
		with self.assertRaises(frappe.PermissionError):
			register.receive(f.name)

	def test_holder_and_movements_cannot_be_edited_by_hand(self):
		a, b = self.USERS
		f = self.file()
		doc = frappe.get_doc("RD File", f.name)
		doc.held_by = b
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		doc = frappe.get_doc("RD File", f.name)
		doc.append("movements", {"from_user": a, "to_user": b})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_a_file_cannot_be_sent_to_someone_not_cleared_for_it(self):
		a, b = self.USERS
		self.clear(a)  # a is cleared for the office, b is not
		f = self.file(classification="Restricted", department=self.DEPT)
		frappe.db.set_value("RD File", f.name, "held_by", a)
		frappe.set_user(a)
		with self.assertRaises(frappe.ValidationError):
			register.send(f.name, b)

	def test_a_file_is_hidden_from_someone_not_cleared(self):
		a, b = self.USERS
		self.clear(a)
		f = self.file(classification="Restricted", department=self.DEPT)
		frappe.set_user(a)
		assert frappe.has_permission("RD File", doc=f.name, user=a)
		assert not frappe.has_permission("RD File", doc=f.name, user=b)
		assert f.name not in frappe.get_list("RD File", user=b, pluck="name")

	def test_a_file_is_at_least_as_restricted_as_its_records(self):
		item = frappe.get_doc(
			{"doctype": "RD Item", "item_id": "rdregtest1", "title": "R", "visibility": "Public"}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "RD Item Scope",
				"item": item.name,
				"classification": "Confidential",
				"department": self.DEPT,
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			self.file(classification="Restricted", department=self.DEPT, records=[{"item": item.name}])
		self.file(
			"RDREGTEST-2", classification="Confidential", department=self.DEPT, records=[{"item": item.name}]
		)

	def test_a_file_is_never_deleted(self):
		f = self.file()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("RD File", f.name, force=True, ignore_permissions=True)

	def test_the_rows_of_a_file_are_hidden_with_the_file(self):
		a, b = self.USERS
		self.clear(a)
		f = self.file(classification="Restricted", department=self.DEPT, notes="x")
		frappe.db.sql(
			"insert into `tabRD File Record` (name, parent, parenttype, parentfield, item, note) "
			"values ('rdregtest-row', %s, 'RD File', 'records', 'rdregtest-x', 'secret note')",
			f.name,
		)
		frappe.set_user(b)
		assert not frappe.get_list("RD File Record", parent_doctype="RD File", fields=["parent"], user=b)
		frappe.set_user(a)
		assert frappe.get_list("RD File Record", parent_doctype="RD File", fields=["parent"], user=a)

	def test_a_number_that_looks_like_the_automatic_one_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.file("F-2026-00001")

	def test_a_holder_can_edit_an_open_file_from_a_form(self):
		a, _b = self.USERS
		f = self.file()
		frappe.db.set_value("RD File", f.name, "held_by", a)
		frappe.set_user(a)
		doc = frappe.get_doc("RD File", f.name)
		doc.opened_on = str(doc.opened_on)  # a form sends dates as text
		doc.notes = "changed by the holder"
		doc.save()
