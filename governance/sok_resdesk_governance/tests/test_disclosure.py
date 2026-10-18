"""0.86: disclosure requests."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from sok_resdesk_governance import disclosure


class TestDisclosure(IntegrationTestCase):
	DEPT = "RD Test Disclosure"
	USER = "rddisclosuretest@example.com"

	def setUp(self):
		self.was = frappe.db.get_single_value("RD Settings", "governance")
		self.days = frappe.db.get_single_value("RD Settings", "disclosure_days")
		frappe.db.set_single_value("RD Settings", "governance", 1)
		frappe.db.set_single_value("RD Settings", "disclosure_days", 10)
		frappe.cache.delete_value("RD Settings")
		frappe.get_doc({"doctype": "RD Department", "department_name": self.DEPT}).insert(
			ignore_permissions=True
		)
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.USER,
				"first_name": "Disc",
				"send_welcome_email": 0,
				"roles": [{"role": "ResDesk Records Officer"}],
			}
		).insert(ignore_permissions=True)
		self.requests = []
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		for n in self.requests:
			frappe.db.delete("RD Disclosure Record", {"parent": n})
			frappe.db.delete("RD Disclosure Redaction", {"parent": n})
			frappe.db.delete("RD Disclosure Request", {"name": n})
		frappe.db.delete("RD Item Scope", {"item": ("like", "rddisctest%")})
		frappe.db.delete("RD Item", {"name": ("like", "rddisctest%")})
		frappe.delete_doc("User", self.USER, force=True, ignore_permissions=True)
		frappe.db.delete("RD Department", {"name": self.DEPT})
		frappe.db.set_single_value("RD Settings", "governance", self.was or 0)
		frappe.db.set_single_value("RD Settings", "disclosure_days", self.days or 30)
		frappe.local.rd_clearance = {}
		frappe.db.commit()

	def item(self, n, classify=False):
		doc = frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": f"rddisctest{n}",
				"title": f"Disclosure {n}",
				"visibility": "Public",
				"published": 1,
			}
		).insert(ignore_permissions=True)
		if classify:
			frappe.get_doc(
				{
					"doctype": "RD Item Scope",
					"item": doc.name,
					"classification": "Restricted",
					"department": self.DEPT,
				}
			).insert(ignore_permissions=True)
		return doc.name

	def request(self, records, **values):
		doc = frappe.get_doc(
			{
				"doctype": "RD Disclosure Request",
				"applicant": "A. Citizen",
				"subject": "Files on the library",
				"records": records,
				**values,
			}
		).insert()
		self.requests.append(doc.name)
		return doc

	def test_a_new_request_is_due_after_the_set_days_and_goes_into_review_with_records(self):
		doc = self.request([{"item": self.item(1), "decision": "Disclose"}])
		assert doc.due_on == add_days(getdate(nowdate()), 10)
		assert doc.status == "In review"

	def test_a_decision_needs_a_ground_to_withhold(self):
		doc = self.request([{"item": self.item(2), "decision": "Withhold"}])
		with self.assertRaises(frappe.ValidationError):
			disclosure.decide(doc.name)
		doc.records[0].ground = "a ground"
		doc.save()
		disclosure.decide(doc.name)
		assert frappe.db.get_value("RD Disclosure Request", doc.name, "status") == "Decided"

	def test_changing_a_decided_request_puts_it_back_in_review(self):
		doc = self.request([{"item": self.item(3), "decision": "Disclose"}])
		disclosure.decide(doc.name)
		doc.reload()
		doc.records[0].decision = "Withhold"
		doc.records[0].ground = "g"
		doc.save()
		assert (doc.status, doc.decided_by) == ("In review", None)

	def test_the_status_is_not_set_by_hand(self):
		doc = self.request([{"item": self.item(4), "decision": "Disclose"}])
		doc.status = "Released"
		doc.save()
		assert doc.status == "In review"

	def test_a_covered_part_needs_a_record_set_to_redacted(self):
		item = self.item(5)
		doc = self.request([{"item": item, "decision": "Disclose"}])
		doc.append("redactions", {"item": item, "page": 1, "left": 10, "top": 10, "width": 20, "height": 5})
		doc.save()
		with self.assertRaises(frappe.ValidationError):
			disclosure.decide(doc.name)

	def test_an_officer_not_cleared_cannot_list_a_classified_record(self):
		secret = self.item(6, classify=True)
		frappe.set_user(self.USER)
		# refused either by the permission rule (it names a record they cannot see) or by the check on save
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self.request([{"item": secret, "decision": "Disclose"}])

	def test_a_request_naming_a_classified_record_is_hidden_from_an_officer_not_cleared(self):
		doc = self.request([{"item": self.item(7, classify=True), "decision": "Disclose"}])
		frappe.set_user(self.USER)
		frappe.local.rd_clearance = {}
		assert doc.name not in frappe.get_list("RD Disclosure Request", pluck="name")
		assert not frappe.has_permission("RD Disclosure Request", "read", doc)

	def test_a_page_to_draw_on_is_refused_to_one_not_cleared_for_the_record(self):
		doc = self.request([{"item": self.item(8, classify=True), "decision": "Disclose redacted"}])
		frappe.set_user("Administrator")
		frappe.local.rd_clearance = {}
		# the Administrator holds no clearance by role: a classified record's page is not shown either
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			disclosure.page_image(doc.name, doc.records[0].item, 1)

	def test_a_page_outside_the_request_is_refused(self):
		doc = self.request([{"item": self.item(9), "decision": "Disclose"}])
		with self.assertRaises(frappe.ValidationError):
			disclosure.page_image(doc.name, "rddisctest-not-on-it", 1)
		with self.assertRaises(frappe.ValidationError):
			disclosure.page_image(doc.name, doc.records[0].item, 0)

	def test_parts_of_a_record_with_no_pdf_cannot_be_covered(self):
		item = self.item(10)  # no file at all, as a photograph or recording would not have a PDF either
		doc = self.request([{"item": item, "decision": "Disclose redacted", "ground": "g"}])
		doc.append("redactions", {"item": item, "page": 1, "left": 10, "top": 10, "width": 20, "height": 5})
		doc.save()
		with self.assertRaises(frappe.ValidationError):
			disclosure.decide(doc.name)

	def test_a_request_is_never_deleted(self):
		doc = self.request([{"item": self.item(8), "decision": "Disclose"}])
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("RD Disclosure Request", doc.name, force=True)
