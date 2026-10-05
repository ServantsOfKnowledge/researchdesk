"""0.47: IIIF manifests, collections and the page image service, answered as the portal answers
(who may see what). Page images are stood in for; the catalogue and the access rules are real."""

import io
import json
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from sok_resdesk import iiif


def jpeg(width=1000, height=1400):
	buf = io.BytesIO()
	Image.new("RGB", (width, height), "white").save(buf, "JPEG")
	return buf.getvalue()


class TestIIIF(IntegrationTestCase):
	def setUp(self):
		self.vis = frappe.db.get_single_value("RD Settings", "guest_access")
		frappe.set_user("Guest")
		self.addCleanup(self._clean)
		frappe.set_user("Administrator")
		self.book("rdtestiiif-ia", source="Internet Archive", on_archive_org=1, page_count=3)
		self.book(
			"rdtestiiif-pdf",
			source="Local",
			local_pdf="rdtest.pdf",
			page_count=2,
			access_status="Open",
			has_page_text=1,
		)
		self.book(
			"rdtestiiif-members",
			source="Internet Archive",
			on_archive_org=1,
			page_count=2,
			visibility="Login to read",
		)
		frappe.get_doc(
			{"doctype": "RD Collection", "title": "rdtest iiif", "slug": "rdtest-iiif", "published": 1}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user("Guest")

	def book(self, item_id, **values):
		frappe.get_doc(
			{
				"doctype": "RD Item",
				"item_id": item_id,
				"title": f"Title of {item_id}",
				"year": 1950,
				"language": "kan",
				"published": 1,
				"visibility": "Public",
				**values,
			}
		).insert(ignore_permissions=True)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.db.delete("RD Item", {"name": ("like", "rdtestiiif%")})
		frappe.db.delete("RD Collection", {"name": "rdtest-iiif"})
		frappe.db.commit()

	def get(self, path, **args):
		resp = iiif.route(path, args)
		return resp.status_code, resp

	def data(self, resp):
		return json.loads(resp.get_data(as_text=True))

	def test_a_book_on_archive_org(self):
		status, resp = self.get("/iiif/rdtestiiif-ia/manifest")
		self.assertEqual(status, 200)
		self.assertIn("presentation/3", resp.headers["Content-Type"])
		self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "*")
		m = self.data(resp)
		self.assertEqual(len(m["items"]), 3)
		image = m["items"][2]["items"][0]["items"][0]["body"]
		self.assertEqual(image["id"], "https://archive.org/download/rdtestiiif-ia/page/n2.jpg")
		self.assertNotIn("service", image)  # archive.org serves these pages
		self.assertTrue(any("iiif.archive.org" in s["id"] for s in m["seeAlso"]))

	def test_a_book_drawn_here_has_an_image_service(self):
		with mock.patch("sok_resdesk.pdfs.page_jpeg", return_value=jpeg()):
			status, resp = self.get("/iiif/rdtestiiif-pdf/manifest")
			self.assertEqual(status, 200)
			m = self.data(resp)
			body = m["items"][0]["items"][0]["items"][0]["body"]
			self.assertTrue(body["id"].endswith("/iiif/image/rdtestiiif-pdf/0/full/max/0/default.jpg"))
			self.assertEqual(body["service"][0]["profile"], "level2")
			self.assertEqual((m["items"][0]["width"], m["items"][0]["height"]), (1000, 1400))
			info = self.data(self.get("/iiif/image/rdtestiiif-pdf/1/info.json")[1])
			self.assertEqual([s["width"] for s in info["sizes"]], [400, 800, 1000])
			status, resp = self.get("/iiif/image/rdtestiiif-pdf/1/full/800,/0/default.jpg")
			self.assertEqual(status, 200)
			self.assertEqual(Image.open(io.BytesIO(resp.get_data())).size, (800, 1120))
			self.assertEqual(self.get("/iiif/image/rdtestiiif-pdf/1/full/max/0/default.jpg")[0], 200)
			# a region, turned and in grey: what a deep-zoom viewer asks for
			status, resp = self.get("/iiif/image/rdtestiiif-pdf/1/100,200,300,400/150,/90/gray.png")
			self.assertEqual(status, 200)
			self.assertEqual(resp.headers["Content-Type"], "image/png")
			self.assertEqual(Image.open(io.BytesIO(resp.get_data())).size, (200, 150))
			self.assertEqual(self.get("/iiif/image/rdtestiiif-pdf/1/full/max/45/default.jpg")[0], 501)
			self.assertEqual(self.get("/iiif/image/rdtestiiif-pdf/1/5000,0,10,10/max/0/default.jpg")[0], 400)
			self.assertEqual(
				self.get("/iiif/image/rdtestiiif-pdf/1/full/2000,/0/default.jpg")[0], 400
			)  # not larger
		# a book on archive.org has no service here
		self.assertEqual(self.get("/iiif/image/rdtestiiif-ia/0/info.json")[0], 404)

	def test_page_text_is_offered_as_annotations(self):
		pages = [{"leaf": 1, "text": "Second page text", "label": "2"}]
		with mock.patch("sok_resdesk.ingest.fetch_pages", return_value=pages):
			data = self.data(self.get("/iiif/rdtestiiif-pdf/text/1")[1])
		self.assertEqual(data["items"][0]["body"]["value"], "Second page text")

	def test_members_only_books_ask_for_a_login_and_are_never_cached_publicly(self):
		status, resp = self.get("/iiif/rdtestiiif-members/manifest")
		self.assertEqual(status, 401)
		frappe.set_user("Administrator")
		status, resp = self.get("/iiif/rdtestiiif-members/manifest")
		self.assertEqual(status, 200)
		self.assertNotIn("Access-Control-Allow-Origin", resp.headers)
		self.assertIn("no-store", resp.headers["Cache-Control"])

	def test_unknown_things_and_collections(self):
		self.assertEqual(self.get("/iiif/nosuchbook/manifest")[0], 404)
		self.assertEqual(self.get("/iiif/rdtestiiif-ia/nonsense")[0], 404)
		top = self.data(self.get("/iiif/collection")[1])
		self.assertEqual(top["type"], "Collection")
		self.assertIn("rdtest-iiif", [i["id"].rsplit("/", 1)[-1] for i in top["items"]])
		self.assertEqual(self.data(self.get("/iiif/collection/rdtest-iiif")[1])["type"], "Collection")
		self.assertEqual(self.get("/iiif/collection/none-such")[0], 404)

	def test_switched_off_with_sharing(self):
		from sok_resdesk import features

		frappe.set_user("Administrator")
		s = frappe.get_single("RD Settings")
		s.feature_sharing = 0
		s.save(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.set_single_value("RD Settings", "feature_sharing", 1))
		self.assertFalse(features.on("sharing"))
		request = mock.Mock(path="/iiif/rdtestiiif-ia/manifest", method="GET", args={})
		with mock.patch.object(frappe, "request", request, create=True):
			with self.assertRaises(iiif.Served) as e:
				iiif.before_request()
		self.assertEqual(e.exception.code, 404)
		frappe.db.set_single_value("RD Settings", "feature_sharing", 1)
		frappe.clear_document_cache("RD Settings", "RD Settings")
		with mock.patch.object(frappe, "request", request, create=True):
			with self.assertRaises(iiif.Served) as e:
				iiif.before_request()
		self.assertEqual(e.exception.code, 200)
