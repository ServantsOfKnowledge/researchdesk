"""Integration tests for the About page (/about, RD About Page). Need a site, no network:

bench --site <site> run-tests --app sok_resdesk --module sok_resdesk.tests.test_about
"""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import about


def top_bar() -> list[tuple[str, str]]:
	ws = frappe.get_single("Website Settings")
	return [(i.label, i.url) for i in sorted(ws.top_bar_items, key=lambda i: i.idx)]


class TestAboutPage(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.saved = frappe.get_single("RD About Page").as_dict(no_default_fields=True)
		cls.saved_bar = top_bar()

	@classmethod
	def tearDownClass(cls):
		doc = frappe.get_single("RD About Page")
		doc.update({k: v for k, v in cls.saved.items() if k not in ("steps", "highlights")})
		doc.set("steps", cls.saved.get("steps") or [])
		doc.set("highlights", cls.saved.get("highlights") or [])
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def page(self, **values):
		doc = frappe.get_single("RD About Page")
		doc.update({"enabled": 1, "nav_label": "About", **values})
		doc.save(ignore_permissions=True)
		return doc

	def test_safe_links(self):
		for ok in ("/library", "/library?q=hampi", "https://archive.org/details/x", "HTTP://example.org"):
			self.assertTrue(about.safe_link(ok), ok)
		for bad in ("javascript:alert(1)", "//evil.example", "data:text/html,x", "ftp://x", ""):
			self.assertFalse(about.safe_link(bad), bad)

	def test_bad_links_are_refused(self):
		doc = frappe.get_single("RD About Page")
		doc.primary_link = "javascript:alert(1)"
		self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)
		doc = frappe.get_single("RD About Page")
		doc.append("steps", {"title": "x", "link": "javascript:alert(1)"})
		self.assertRaises(frappe.ValidationError, doc.save, ignore_permissions=True)

	def test_top_bar_link_follows_the_page(self):
		self.page(nav_label="About us")
		bar = top_bar()
		self.assertIn(("About us", "/about"), bar)
		self.assertEqual(sum(1 for _, url in bar if url == "/about"), 1)
		urls = [url for _, url in bar]
		if "/library" in urls:  # right after Library
			self.assertEqual(urls.index("/about"), urls.index("/library") + 1)
		self.page(enabled=0)
		self.assertNotIn("/about", [url for _, url in top_bar()])
		self.page(nav_label="About")
		self.assertIn(("About", "/about"), top_bar())

	def test_content_is_made_safe(self):
		self.page(
			headline="Our <b>library</b>",
			intro='<p>Hello</p><script>alert(1)</script><img src="/x.png" onerror="alert(2)">',
			body="<p>&nbsp;</p>",
			show_stats=0,
			show_collections=0,
			steps=[{"title": "Search", "text": "Use **Inside the text** <i>now</i>", "link": "/library"}],
		)
		frappe.clear_document_cache("RD About Page", "RD About Page")
		ctx = about.context()
		self.assertNotIn("<script", ctx.intro)
		self.assertNotIn("onerror", ctx.intro)
		self.assertIn("Hello", ctx.intro)
		self.assertEqual(ctx.body, "")  # an empty editor shows nothing
		self.assertEqual(ctx.steps[0].text, "Use <strong>Inside the text</strong> &lt;i&gt;now&lt;/i&gt;")
		self.assertEqual(ctx.numbers, [])
		from frappe.website.serve import get_response_content

		frappe.set_user("Guest")
		try:
			html = get_response_content("about")
		finally:
			frappe.set_user("Administrator")
		self.assertIn("Our &lt;b&gt;library&lt;/b&gt;", html)
		self.assertNotIn("<script>alert", html)
		self.assertIn('href="/library"', html)

	def test_switched_off_page_sends_visitors_to_the_library(self):
		from frappe.website.serve import get_response

		self.page(enabled=0)
		frappe.set_user("Guest")
		try:
			response = get_response("about")
		finally:
			frappe.set_user("Administrator")
		self.assertIn(response.status_code, (301, 302))
		self.assertTrue(response.headers["Location"].endswith("/library"))

	def test_defaults_and_buttons(self):
		self.page(primary_label="Open the library", primary_link="/library", secondary_label="", show_stats=1)
		frappe.clear_document_cache("RD About Page", "RD About Page")
		ctx = about.context()
		self.assertEqual(
			[(b.label, b.link, b.primary) for b in ctx.buttons], [("Open the library", "/library", True)]
		)
		self.assertTrue(ctx.numbers and ctx.numbers[0][1] == "books")
		self.assertTrue(ctx.title.startswith("About "))
		self.assertTrue(frappe.db.get_default("resdesk_about_set_up"))
