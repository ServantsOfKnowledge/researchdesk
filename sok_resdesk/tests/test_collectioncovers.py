"""0.44: a collection's picture from archive.org, and a librarian's own never overwritten."""

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import collectioncovers

def tiny_image(fmt="JPEG"):
	import io

	from PIL import Image

	out = io.BytesIO()
	Image.new("RGB", (4, 4), "teal").save(out, fmt)
	return out.getvalue()


JPEG, PNG = tiny_image(), tiny_image("PNG")


class FakeIA:
	def __init__(self, image=(JPEG, "jpg")):
		self.image, self.asked = image, []

	def collection_image(self, identifier):
		self.asked.append(identifier)
		return self.image


class TestCollectionCovers(IntegrationTestCase):
	def setUp(self):
		self.ia = FakeIA()
		p = mock.patch("sok_resdesk.ingest.client", side_effect=lambda: self.ia)
		p.start()
		self.addCleanup(p.stop)
		self.coll = frappe.get_doc(
			{"doctype": "RD Collection", "title": "rdtest covers", "slug": "rdtest-covers", "mirror_of": "rdtestcovers"}
		).insert(ignore_permissions=True)
		self.addCleanup(self._clean)

	def _clean(self):
		for f in frappe.get_all("File", filters={"attached_to_name": self.coll.name}, pluck="name"):
			frappe.delete_doc("File", f, force=True, ignore_permissions=True)
		frappe.db.delete("RD Collection", self.coll.name)
		frappe.db.commit()

	def cover(self):
		return frappe.db.get_value("RD Collection", self.coll.name, ["cover_image", "source_cover"])

	def test_missing_covers_come_from_archive_org_and_own_ones_stay(self):
		self.assertEqual(collectioncovers.fill_missing([self.coll.name]), 1)
		first, ours = self.cover()
		self.assertEqual(first, ours)
		self.assertEqual(frappe.db.get_value("File", {"file_url": first}, "attached_to_name"), self.coll.name)
		# taken again (the button): the new file replaces ours, the old one is gone
		self.ia.image = (PNG, "png")
		self.assertTrue(collectioncovers.get_image(self.coll.name)["ok"])
		second = self.cover()[0]
		self.assertTrue(second.endswith(".png"))
		self.assertFalse(frappe.db.exists("File", {"file_url": first}))
		# a librarian's own image is never replaced automatically
		frappe.db.set_value("RD Collection", self.coll.name, "cover_image", "/files/our-own.jpg")
		self.assertFalse(collectioncovers.fetch(self.coll.name)["ok"])
		self.assertEqual(self.cover()[0], "/files/our-own.jpg")

	def test_unticked_or_nothing_on_archive_org_leaves_it_empty(self):
		frappe.db.set_value("RD Collection", self.coll.name, "image_source", 0)
		self.assertEqual(collectioncovers.fill_missing([self.coll.name]), 0)
		self.assertEqual(self.ia.asked, [])
		frappe.db.set_value("RD Collection", self.coll.name, "image_source", 1)
		self.ia.image = None
		self.assertEqual(collectioncovers.fill_missing([self.coll.name]), 0)
		self.assertEqual(self.cover(), (None, None))
		# a damaged answer is no image, not an error
		self.ia.image = (b"\xff\xd8\xff\xe0broken", "jpg")
		self.assertFalse(collectioncovers.get_image(self.coll.name)["ok"])

	def test_any_identifier_for_a_curated_collection(self):
		frappe.db.set_value("RD Collection", self.coll.name, "mirror_of", None)
		self.assertTrue(collectioncovers.get_image(self.coll.name, "servantsofknowledge")["ok"])
		self.assertEqual(self.ia.asked, ["servantsofknowledge"])
		self.assertEqual(frappe.db.get_value("RD Collection", self.coll.name, "image_from"), "servantsofknowledge")
