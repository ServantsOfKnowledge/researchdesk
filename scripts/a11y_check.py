#!/usr/bin/env python3
"""Accessibility checks on a running Research Desk (CI, or by hand against any install).

Opens the portal's pages, and the Desk's Research Desk pages when a password is given, in a
browser and runs axe-core on each: WCAG 2.0, 2.1 and 2.2, levels A and AA. A *serious* or
*critical* problem fails the check; moderate and minor ones are listed. On the Desk only our own
page is checked (Frappe's menus and side bar are Frappe's).

    pip install playwright && python -m playwright install --with-deps chromium
    npm pack axe-core@4  &&  tar xzf axe-core-*.tgz          # gives package/axe.min.js
    python scripts/a11y_check.py http://localhost:8080 --axe package/axe.min.js \\
        [--password ADMIN_PASSWORD] [--report a11y-report.json]

Exit status 1 when a page has a serious or critical problem. See docs/accessibility.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
FAIL_ON = {"serious", "critical"}

PORTAL = [
	("Home and search", "/"),
	("Search results", "/?q=india"),
	("Search inside the text", "/?q=india&mode=pages"),
	("Collections", "/library/collections"),
	("About", "/about"),
	("Help", "/library/help"),
]
DESK = [
	("Server", "/app/resdesk-server", "#page-resdesk-server .layout-main-section"),
	("People & Roles", "/app/resdesk-people", "#page-resdesk-people .layout-main-section"),
	("Background Jobs", "/app/resdesk-jobs", "#page-resdesk-jobs .layout-main-section"),
	("Portal Translations", "/app/resdesk-translations", "#page-resdesk-translations .layout-main-section"),
	("Authorities", "/app/resdesk-authorities", "#page-resdesk-authorities .layout-main-section"),
	("Review Queue", "/app/resdesk-review", "#page-resdesk-review .layout-main-section"),
	("Connections", "/app/resdesk-connections", "#page-resdesk-connections .layout-main-section"),
	("Help", "/app/resdesk-help", "#page-resdesk-help .layout-main-section"),
]


def first_book(base: str) -> str | None:
	"""The first book the search finds whose page opens (the index can hold a book a test
	deleted a moment ago)."""
	try:
		with urllib.request.urlopen(
			f"{base}/api/method/sok_resdesk.api.search?q=&per_page=20", timeout=30
		) as r:
			hits = json.load(r)["message"]["hits"]
	except Exception:
		return None
	for hit in hits:
		try:
			with urllib.request.urlopen(f"{base}/library/item/{hit['item_id']}", timeout=30) as r:
				if r.status == 200:
					return hit["item_id"]
		except Exception:
			continue
	return None


def run_axe(page, axe: str, include: str | None) -> list[dict]:
	page.add_script_tag(content=axe)
	return page.evaluate(
		"""async ([include, tags]) => {
			const ctx = include ? { include: [include] } : document;
			const r = await axe.run(ctx, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] });
			return r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, url: v.helpUrl,
				nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target.join(" "), html: n.html.slice(0, 200) })) }));
		}""",
		[include, TAGS],
	)


def main() -> int:
	ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
	ap.add_argument("base", help="the site, e.g. http://localhost:8080")
	ap.add_argument("--axe", required=True, help="path to axe.min.js")
	ap.add_argument("--password", help="Administrator's password, to check the Desk pages too")
	ap.add_argument("--report", help="write every finding to this JSON file")
	ap.add_argument("--browser", help="a Chromium to use instead of Playwright's own")
	args = ap.parse_args()
	base = args.base.rstrip("/")
	axe = open(args.axe, encoding="utf-8").read()

	from playwright.sync_api import sync_playwright

	pages = [(name, path, None) for name, path in PORTAL]
	book = first_book(base)
	if book:
		pages += [("Book page", f"/library/item/{book}", None)]
	# the reading settings' colours (a11y.js), on the busiest pages
	colours = [(mode, path) for mode in ("contrast", "dark", "sepia") for path in ("/", pages[-1][1])]
	report, failed = [], False
	with sync_playwright() as p:
		browser = p.chromium.launch(executable_path=args.browser) if args.browser else p.chromium.launch()
		for width in (1280, 390):
			ctx = browser.new_context(viewport={"width": width, "height": 900})
			page = ctx.new_page()
			for name, path, include in pages:
				page.goto(base + path, wait_until="networkidle")
				found = run_axe(page, axe, include)
				report.append({"page": name, "path": path, "width": width, "violations": found})
			ctx.close()
		ctx = browser.new_context(viewport={"width": 1280, "height": 900})
		page = ctx.new_page()
		for mode, path in colours:
			page.goto(base + "/")
			page.evaluate(
				"(m) => localStorage.setItem('rd-reading', JSON.stringify({ colours: m, size: 'xl', spacing: 'wide' }))",
				mode,
			)
			page.goto(base + path, wait_until="networkidle")
			found = run_axe(page, axe, None)
			report.append({"page": f"Colours: {mode}", "path": path, "width": 1280, "violations": found})
		ctx.close()
		if args.password:
			ctx = browser.new_context(viewport={"width": 1280, "height": 900})
			page = ctx.new_page()
			page.goto(base + "/login")
			resp = page.request.post(
				base + "/api/method/login", form={"usr": "Administrator", "pwd": args.password}
			)
			desk = DESK if resp.ok else []
			if not resp.ok:
				print("Could not log in to check the Desk pages", file=sys.stderr)
				failed = True
			if book:  # Page & text is for logged-in members: checked as one
				page.goto(base + f"/library/item/{book}?view=text", wait_until="networkidle")
				found = run_axe(page, axe, None)
				report.append(
					{
						"page": "Page & text (logged in)",
						"path": f"/library/item/{book}?view=text",
						"width": 1280,
						"violations": found,
					}
				)
			page.goto(base + "/library/profile", wait_until="networkidle")  # About me, for members
			page.wait_for_function("document.getElementById('rd-pf').getAttribute('aria-busy') === 'false'")
			report.append(
				{
					"page": "About me (logged in)",
					"path": "/library/profile",
					"width": 1280,
					"violations": run_axe(page, axe, None),
				}
			)
			for name, path, include in desk:
				page.goto(base + path, wait_until="networkidle")
				page.wait_for_selector(include, timeout=20000)
				page.wait_for_timeout(800)  # the page fills itself in
				found = run_axe(page, axe, include)
				report.append({"page": f"Desk: {name}", "path": path, "width": 1280, "violations": found})
			ctx.close()
		browser.close()

	for r in report:
		bad = [v for v in r["violations"] if v["impact"] in FAIL_ON]
		failed = failed or bool(bad)
		mark = "FAIL" if bad else "ok  "
		print(f"{mark} {r['page']} ({r['path']}, {r['width']} px): {len(r['violations'])} finding(s)")
		for v in r["violations"]:
			print(f"     [{v['impact']}] {v['id']}: {v['help']}")
			for n in v["nodes"][:3]:
				print(f"         {n['target']}  {n['html'][:120]}")
	if args.report:
		with open(args.report, "w", encoding="utf-8") as f:
			json.dump(report, f, indent=1, ensure_ascii=False)
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
