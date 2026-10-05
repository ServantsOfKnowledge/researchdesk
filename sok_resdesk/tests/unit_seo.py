"""Findable and safe (core/seo.py) and fetching outside addresses safely (core/netguard.py)."""

import socket

import pytest

from sok_resdesk.core import netguard, seo


def test_robots_keeps_crawlers_out_of_the_desk_and_searches():
	text = seo.robots_txt("https://lib.example/", "Disallow: /drafts")
	assert "Disallow: /app" in text and "Disallow: /api/" in text
	assert "Allow: /api/method/sok_resdesk.api.cite" in text
	assert "Disallow: /*?*q=" in text
	assert "Disallow: /drafts" in text  # the library's own lines
	assert text.rstrip().endswith("Sitemap: https://lib.example/sitemap.xml")


def test_sitemaps():
	xml = seo.urlset([("https://lib.example/library/item/a&b", "2026-10-01"), ("https://lib.example/", "")])
	assert "<loc>https://lib.example/library/item/a&amp;b</loc><lastmod>2026-10-01</lastmod>" in xml
	assert "<url><loc>https://lib.example/</loc></url>" in xml
	assert "<sitemapindex" in seo.sitemap_index([("https://lib.example/sitemap.xml?part=1", "")])
	assert seo.book_url("https://lib.example", "a b/c") == "https://lib.example/library/item/a%20b%2Fc"


def test_descriptions_say_what_the_book_is():
	rec = {"creators": ["Kanakadasa"], "year": 1931, "language_label": "Kannada", "has_page_text": True}
	text = seo.describe(rec, "SOK Research Desk")
	assert (
		text
		== "A book by Kanakadasa from 1931 in Kannada. Read it and search inside its text, page by page, at SOK Research Desk."
	)
	own = "x " * 200
	assert len(seo.describe({"description": own})) <= seo.DESCRIPTION
	assert seo.describe(
		{"description": "<p>A long description of the book, its contents and its history</p>"}
	).startswith("A long")


def test_language_alternates_and_head():
	alt = seo.alternates(
		"https://lib.example", "library/item/x", ["kn", "hi"], {"_lang": "kn", "view": "text"}
	)
	assert alt[0] == ("x-default", "https://lib.example/library/item/x?view=text")
	assert ("kn", "https://lib.example/library/item/x?view=text&_lang=kn") in alt
	assert seo.alternates("https://lib.example", "", [], {}) == []
	head = seo.head_links("https://lib.example/", alt[:1], noindex=True)
	assert '<link rel="canonical" href="https://lib.example/">' in head
	assert 'content="noindex,follow"' in head
	data = seo.website_json_ld("https://lib.example", "Library")
	assert (
		data["potentialAction"]["target"]["urlTemplate"]
		== "https://lib.example/library?q={search_term_string}"
	)


def test_security_headers():
	h = seo.security_headers(https=True, desk=False)
	assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "SAMEORIGIN"
	assert (
		"frame-ancestors 'self'" in h["Content-Security-Policy"]
		and "form-action" in h["Content-Security-Policy"]
	)
	assert "Strict-Transport-Security" in h
	assert "Strict-Transport-Security" not in seo.security_headers(https=False, desk=True)


def fake_resolve(table):
	def resolve(host, port):
		return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], port))]

	return resolve


def test_outside_addresses_must_be_public():
	resolve = fake_resolve(
		{"repo.example.org": "93.184.216.34", "evil.example": "169.254.169.254", "lan": "10.0.0.5"}
	)
	assert netguard.check("https://repo.example.org/x.pdf", resolve=resolve)
	for url in (
		"http://evil.example/latest/meta-data",
		"http://lan/x",
		"file:///etc/passwd",
		"ftp://repo.example.org/x",
	):
		with pytest.raises(netguard.Blocked):
			netguard.check(url, resolve=resolve)
	# a repository the library set up on its own network is trusted
	assert netguard.check("http://lan/oai", trusted_hosts=("lan",), resolve=resolve)


def test_redirects_are_checked_at_every_hop(monkeypatch):
	class Resp:
		def __init__(self, status, location=""):
			self.status_code, self.headers = status, {"Location": location} if location else {}

		def close(self):
			pass

	class Session:
		def __init__(self):
			self.asked = []

		def get(self, url, **kw):
			self.asked.append(url)
			return Resp(302, "http://lan/secret") if url.endswith("/start") else Resp(200)

	monkeypatch.setattr(
		netguard,
		"check",
		lambda url, trusted=(): (_ for _ in ()).throw(netguard.Blocked("private")) if "lan" in url else url,
	)
	s = Session()
	with pytest.raises(netguard.Blocked):
		netguard.get(s, "https://repo.example.org/start")
	assert s.asked == ["https://repo.example.org/start"]  # the private hop is never asked
