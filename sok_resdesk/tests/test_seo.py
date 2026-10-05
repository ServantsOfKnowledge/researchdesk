"""0.41: findable and secure. robots.txt and the sitemap from the catalogue, what portal pages
tell search engines, security headers, the Server page's security checks."""

from types import SimpleNamespace

import frappe

from sok_resdesk.tests.test_operations import OpsTestCase, _item


class TestFindable(OpsTestCase):
	def setUp(self):
		super().setUp()
		self._guest = frappe.db.get_single_value("RD Settings", "guest_access")
		self.addCleanup(lambda: frappe.db.set_single_value("RD Settings", "guest_access", self._guest))

	def test_robots_and_sitemap(self):
		from sok_resdesk import seo
		from sok_resdesk.core.access import GUEST_NONE

		name = _item(1)
		frappe.db.set_value("RD Item", name, {"published": 1, "visibility": "Public"})
		text = seo.robots()
		self.assertIn("Disallow: /app", text)
		self.assertIn("/sitemap.xml", text)
		index = seo.sitemap(0)
		self.assertIn("sitemap.xml?part=1", index)
		self.assertIn("sitemap.xml?part=pages", index)
		part = seo.sitemap(1)
		self.assertIn(f"/library/item/{name}</loc>", part)
		self.assertIn("/library/collections</loc>", seo.sitemap("pages"))
		# a members-only portal tells search engines nothing
		frappe.db.set_single_value("RD Settings", "guest_access", GUEST_NONE)
		frappe.clear_document_cache("RD Settings", "RD Settings")
		self.assertEqual(seo.robots(), "User-agent: *\nDisallow: /\n")
		self.assertNotIn("<url>", seo.sitemap(1))

	def test_portal_pages_head(self):
		from sok_resdesk import seo

		frappe.local.form_dict = frappe._dict()
		head = seo.website_context(
			{"path": "library/item/x", "portal_url": "https://lib.example/library/item/x"}
		)
		self.assertIn(
			'<link rel="canonical" href="https://lib.example/library/item/x">', head["head_include"]
		)
		self.assertNotIn("noindex", head["head_include"])
		frappe.local.form_dict = frappe._dict(q="kanakadasa")
		head = seo.website_context({"path": "library"})
		self.assertIn('content="noindex,follow"', head["head_include"])
		frappe.local.form_dict = frappe._dict()
		home = seo.website_context({"path": ""})
		self.assertIn('"@type": "WebSite"', home["head_include"])
		self.assertIsNone(seo.website_context({"path": "app/rd-item"}))

	def test_book_pages_describe_themselves(self):
		from sok_resdesk.catalogue import item_to_record
		from sok_resdesk.core.seo import describe

		record = item_to_record(frappe.get_doc("RD Item", _item(2)))
		self.assertIn("Test Author", describe(record, "Portal"))


class TestSecure(OpsTestCase):
	def test_headers_on_every_response(self):
		from sok_resdesk import security

		response = SimpleNamespace(headers={})
		request = SimpleNamespace(path="/library", scheme="http", headers={"X-Forwarded-Proto": "https"})
		security.add_headers(response, request)
		self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
		self.assertIn("Strict-Transport-Security", response.headers)
		kept = SimpleNamespace(headers={"X-Frame-Options": "DENY"})
		security.add_headers(kept, request)
		self.assertEqual(kept.headers["X-Frame-Options"], "DENY")  # something that set its own keeps it

	def test_logins_hardened_and_checked(self):
		from sok_resdesk import security

		s = frappe.get_single("System Settings")
		saved = (s.allow_consecutive_login_attempts, s.allow_login_after_fail)
		self.addCleanup(
			lambda: frappe.db.set_single_value(
				"System Settings",
				{"allow_consecutive_login_attempts": saved[0], "allow_login_after_fail": saved[1]},
			)
		)
		frappe.db.set_single_value(
			"System Settings", {"allow_consecutive_login_attempts": 10, "allow_login_after_fail": 60}
		)
		security.harden_logins()
		s = frappe.get_single("System Settings")
		self.assertEqual((s.allow_consecutive_login_attempts, s.allow_login_after_fail), (5, 300))
		checks = {c["key"]: c for c in security.checks()}
		self.assertEqual(
			set(checks)
			>= {"https", "admin_password", "developer_mode", "lockout", "two_factor", "search_key"},
			True,
		)
		self.assertEqual(checks["lockout"]["state"], "ok")
		from sok_resdesk.server import health

		self.assertIn("admin_password", {c["key"] for c in health()})
