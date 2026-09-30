#!/usr/bin/env python3
"""Retake the screenshots used in the guides (docs/*.md) from a running Research Desk.

    ./resdesk.sh screenshots                     # uses http://localhost:<HTTP_PORT> and .env
    python3 scripts/screenshots.py --url https://library.example.org --password …

Needs Playwright:  pip install playwright && python3 -m playwright install chromium
Pictures go to sok_resdesk/public/images/guide/ (served at /assets/sok_resdesk/images/guide/).
Run it after changing a screen, look at `git diff --stat`, and commit the new pictures with the
change. tests/test_docs.py checks that every picture the docs use is listed here and exists.

The screens look best with some books, a collection and a profile in the catalogue, and a
query that finds something (--query).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sok_resdesk" / "public" / "images" / "guide"
VIEWPORT = {"width": 1280, "height": 800}

# name -> (who, what to open, what to do before the picture). "who" is guest or staff.
SHOTS: dict[str, tuple[str, str, str]] = {
	"portal-home": ("guest", "/library?tips=1", ""),
	"portal-results": ("guest", "/library?q={query}", "results"),
	"portal-collection": ("guest", "/library/collections", "click:.rd-coll-card"),
	"portal-book": ("guest", "/library?q={query}", "click:.rd-hit h3 a"),
	"portal-mylist": ("guest", "/library?q={query}", "mylist"),
	"portal-help": ("guest", "/library/help", ""),
	"desk-workspace": ("staff", "/app/research-desk", ""),
	"desk-help": ("staff", "/app/resdesk-help/staff-guide", ""),
	"desk-profile": ("staff", "/app/rd-ingest-profile", "open-first"),
	"desk-tour": ("staff", "/app/rd-ingest-profile/new", "tour"),
	"desk-jobs": ("staff", "/app/resdesk-jobs", ""),
	"desk-items": ("staff", "/app/rd-item", ""),
	"desk-collection": ("staff", "/app/rd-collection", "open-first"),
	"desk-settings": ("staff", "/app/rd-settings", ""),
}


def env_file() -> dict:
	out = {}
	path = ROOT / ".env"
	if path.exists():
		for line in path.read_text().splitlines():
			if "=" in line and not line.lstrip().startswith("#"):
				k, v = line.split("=", 1)
				out[k.strip()] = v.strip().strip('"').strip("'")
	return out


async def take(args) -> list[str]:
	from playwright.async_api import async_playwright

	OUT.mkdir(parents=True, exist_ok=True)
	done = []
	async with async_playwright() as p:
		browser = await p.chromium.launch()
		guest = await browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme=args.theme)
		# the first-visit tips only on the home-page picture (it asks for them with ?tips=1)
		await guest.add_init_script("try { localStorage.setItem('rd-tips-seen', '1') } catch (e) {}")
		staff = await browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme=args.theme)
		login = await staff.new_page()
		await login.goto(f"{args.url}/login")
		await login.fill("#login_email", args.user)
		await login.fill("#login_password", args.password)
		await login.click(".btn-login")
		await login.wait_for_timeout(3000)
		await login.close()

		for name, (who, path, action) in SHOTS.items():
			if args.only and name not in args.only:
				continue
			page = await (guest if who == "guest" else staff).new_page()
			try:
				await page.goto(args.url + path.format(query=args.query))
				await page.wait_for_timeout(2500)
				if action == "results":
					await page.wait_for_selector(".rd-hit", timeout=15000)
					await page.evaluate("window.scrollTo(0, document.querySelector('.rd-layout').offsetTop - 70)")
				elif action.startswith("click:"):
					await page.wait_for_selector(action[6:], timeout=15000)
					await page.click(action[6:])
					await page.wait_for_timeout(3500)
				elif action == "open-first":
					await page.wait_for_selector(".list-row-container a.ellipsis", timeout=15000)
					await page.click(".list-row-container a.ellipsis")
					await page.wait_for_timeout(3000)
				elif action == "tour":
					await page.wait_for_function("window.cur_frm && cur_frm.doctype === 'RD Ingest Profile'", timeout=15000)
					await page.evaluate("cur_frm.tour.init({tour_name: cur_frm.doctype}).then(() => cur_frm.tour.start())")
					await page.wait_for_timeout(1500)
				elif action == "mylist":
					await page.wait_for_selector(".rd-save", timeout=15000)
					for button in (await page.query_selector_all(".rd-save"))[:3]:
						await button.click()
					await page.evaluate("window.scrollTo(0, document.querySelector('.rd-layout').offsetTop - 70)")
					await page.click("#rd-basket-btn")
					await page.wait_for_timeout(800)
				await page.wait_for_timeout(1000)
				target = OUT / f"{name}.png"
				await page.screenshot(path=str(target))
				shrink(target)
				done.append(name)
				print(f"  ✓ {name}")
			except Exception as e:  # keep going: one missing screen shouldn't stop the rest
				print(f"  ✗ {name}: {e}", file=sys.stderr)
			finally:
				await page.close()
		await browser.close()
	return done


def shrink(path: Path) -> None:
	"""Fewer colours, same look: screenshots of the UI compress 3–5x this way."""
	try:
		from PIL import Image
	except ImportError:
		return
	img = Image.open(path).convert("RGB")
	img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def main() -> int:
	env = env_file()
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--url", default=os.environ.get("RD_URL") or f"http://localhost:{env.get('HTTP_PORT', '8080')}")
	ap.add_argument("--user", default=os.environ.get("RD_USER", "Administrator"))
	ap.add_argument("--password", default=os.environ.get("RD_PASSWORD") or env.get("ADMIN_PASSWORD", "admin"))
	ap.add_argument("--query", default=os.environ.get("RD_QUERY", "history"),
					help="a search that finds books in your catalogue (default: history)")
	ap.add_argument("--theme", choices=["light", "dark"], default="light")
	ap.add_argument("only", nargs="*", help=f"only these pictures: {', '.join(SHOTS)}")
	args = ap.parse_args()
	try:
		import playwright  # noqa: F401
	except ImportError:
		print("Needs Playwright: pip install playwright && python3 -m playwright install chromium", file=sys.stderr)
		return 1
	print(f"Taking screenshots of {args.url} into {OUT.relative_to(ROOT)}/")
	done = asyncio.run(take(args))
	wanted = len(args.only or SHOTS)
	print(f"{len(done)} of {wanted} taken.")
	return 0 if len(done) == wanted else 1


if __name__ == "__main__":
	sys.exit(main())
