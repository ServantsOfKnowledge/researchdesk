#!/usr/bin/env python3
"""Retake the screenshots used in the guides (docs/*.md) from a running Research Desk.

    ./resdesk.sh screenshots                     # uses http://localhost:<HTTP_PORT> and .env
    python3 scripts/screenshots.py --url https://library.example.org --password …

Needs Playwright:  pip install playwright && python3 -m playwright install chromium
(or CHROMIUM_PATH=/path/to/chrome for a Chromium already installed)
(./resdesk.sh screenshots uses Playwright's own Docker image when this machine has no Playwright,
and with --site puts the pictures into the library's help instead: the Server page's
*Retake help pictures* button does that.)
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
	"portal-home": ("guest", "/?tips=1", ""),
	"portal-results": ("guest", "/?q={query}", "results"),
	"portal-collection": ("guest", "/library/collections", "click:.rd-coll-card"),
	"portal-book": ("guest", "/?q={query}", "click:.rd-hit h3 a"),
	"portal-mylist": ("guest", "/?q={query}", "mylist"),
	"portal-help": ("guest", "/library/help", ""),
	"portal-about": ("guest", "/about", ""),
	"desk-workspace": ("staff", "/app/research-desk", ""),
	"desk-help": ("staff", "/app/resdesk-help/staff-guide", ""),
	"desk-profile": ("staff", "/app/rd-ingest-profile", "open-first"),
	"desk-tour": ("staff", "/app/rd-ingest-profile/new", "tour"),
	"desk-jobs": ("staff", "/app/resdesk-jobs", ""),
	"desk-machine": ("staff", "/app/resdesk-jobs", "machine"),
	"desk-server": ("staff", "/app/resdesk-server", ""),
	"desk-items": ("staff", "/app/rd-item", ""),
	"desk-collection": ("staff", "/app/rd-collection", "open-first"),
	"desk-settings": ("staff", "/app/rd-settings", ""),
	"desk-about": ("staff", "/app/rd-about-page", "scroll:[data-fieldname=section_steps]"),
	"desk-library-system": ("staff", "/app/rd-library-system", "open-first"),
}

# The Desk pictures show what staff see. Administrator sees Frappe's own tools too (Settings → The
# Desk), so when the pictures are taken with Administrator's password, they are taken as this
# staff account instead: made (or switched on) for the pictures and switched off afterwards.
PICTURE_ACCOUNT = "help-pictures@example.org"
STAFF_ROLES = ("ResDesk Manager", "ResDesk Cataloguer")


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

	out = Path(args.out)
	out.mkdir(parents=True, exist_ok=True)
	done = []
	async with async_playwright() as p:
		# CHROMIUM_PATH: a Chromium already on the machine, when Playwright's own download is missing
		browser = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
		guest = await browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme=args.theme)
		# the first-visit tips only on the home-page picture (it asks for them with ?tips=1)
		await guest.add_init_script("try { localStorage.setItem('rd-tips-seen', '1') } catch (e) {}")
		admin = await browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme=args.theme)
		await log_in(admin, args.url, args.user, args.password)
		staff, account = admin, None
		if args.user == "Administrator":
			account = await picture_account(admin, args.url, on=True)
			staff = await browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme=args.theme)
			await log_in(staff, args.url, PICTURE_ACCOUNT, account)

		for name, (who, path, action) in SHOTS.items():
			if args.only and name not in args.only:
				continue
			page = await (guest if who == "guest" else staff).new_page()
			try:
				await page.goto(args.url + path.format(query=args.query))
				await page.wait_for_timeout(2500)
				if action == "results":
					await page.wait_for_selector(".rd-hit", timeout=15000)
					await page.evaluate(
						"window.scrollTo(0, document.querySelector('.rd-layout').offsetTop - 70)"
					)
				elif action.startswith("click:"):
					await page.wait_for_selector(action[6:], timeout=15000)
					await page.click(action[6:])
					await page.wait_for_timeout(3500)
				elif action == "open-first":
					await page.wait_for_selector(".list-row-container a.ellipsis", timeout=15000)
					await page.click(".list-row-container a.ellipsis")
					await page.wait_for_timeout(3000)
				elif action.startswith("scroll:"):
					await page.wait_for_selector(action[7:], timeout=15000)
					await page.evaluate(f"document.querySelector({action[7:]!r}).scrollIntoView()")
					await page.wait_for_timeout(800)
				elif action == "machine":
					await page.wait_for_timeout(4000)  # two samples, for CPU per part
					await page.evaluate("""[...document.querySelectorAll('.rdj-card h4')].find(h => h.textContent.trim() === 'Machine')
						.closest('.rdj-card').scrollIntoView({block: 'end'})""")
				elif action == "tour":
					await page.wait_for_function(
						"window.cur_frm && cur_frm.doctype === 'RD Ingest Profile'", timeout=15000
					)
					await page.evaluate(
						"cur_frm.tour.init({tour_name: cur_frm.doctype}).then(() => cur_frm.tour.start())"
					)
					await page.wait_for_timeout(1500)
				elif action == "mylist":
					await page.wait_for_selector(".rd-save", timeout=15000)
					for button in (await page.query_selector_all(".rd-save"))[:3]:
						await button.click()
					await page.evaluate(
						"window.scrollTo(0, document.querySelector('.rd-layout').offsetTop - 70)"
					)
					await page.click("#rd-basket-btn")
					await page.wait_for_timeout(800)
				await page.wait_for_timeout(1000)
				target = out / f"{name}.png"
				await page.screenshot(path=str(target))
				shrink(target)
				done.append(name)
				print(f"  ✓ {name}")
			except Exception as e:  # keep going: one missing screen shouldn't stop the rest
				print(f"  ✗ {name}: {e}", file=sys.stderr)
			finally:
				await page.close()
		if account:
			await picture_account(admin, args.url, on=False)
		await browser.close()
	return done


async def log_in(context, url: str, user: str, password: str) -> None:
	page = await context.new_page()
	await page.goto(f"{url}/login")
	await page.fill("#login_email", user)
	await page.fill("#login_password", password)
	await page.click(".btn-login")
	await page.wait_for_timeout(3000)
	await page.close()


async def picture_account(admin, url: str, on: bool) -> str:
	"""Switch the pictures' staff account on (made the first time, a new password each run) or off.
	Done through the Desk's own calls, as Administrator. Returns the password."""
	import secrets

	password = secrets.token_urlsafe(18) + "-Rd7"
	page = await admin.new_page()
	try:
		await page.goto(f"{url}/app/user")
		await page.wait_for_function("window.frappe && frappe.csrf_token", timeout=20000)
		await page.evaluate(
			"""async ([email, password, roles, on]) => {
				const exists = await frappe.xcall('frappe.client.get_count', {doctype: 'User', filters: {name: email}});
				if (!on) {
					if (exists) await frappe.xcall('frappe.client.set_value', {doctype: 'User', name: email, fieldname: 'enabled', value: 0});
					return;
				}
				if (exists) {
					await frappe.xcall('frappe.client.set_value', {doctype: 'User', name: email, fieldname: {enabled: 1, new_password: password}});
				} else {
					await frappe.xcall('frappe.client.insert', {doc: {doctype: 'User', email, first_name: 'Help', last_name: 'Pictures',
						language: 'en', send_welcome_email: 0, new_password: password, roles: roles.map(role => ({role}))}});
				}
			}""",
			[PICTURE_ACCOUNT, password, list(STAFF_ROLES), on],
		)
	finally:
		await page.close()
	return password


def record_taken(out: Path, done: list[str]) -> None:
	"""For a library's own pictures (--out elsewhere): which shipped picture each one stands in for,
	so the help goes back to the shipped one once an upgrade changes it (sok_resdesk/help.py)."""
	import hashlib
	import json

	taken = {}
	for name in done:
		shipped = OUT / f"{name}.png"
		taken[f"{name}.png"] = hashlib.sha256(shipped.read_bytes()).hexdigest() if shipped.exists() else ""
	(out / "taken.json").write_text(json.dumps(taken, indent=1))


def shrink(path: Path) -> None:
	"""Fewer colours, same look: screenshots of the UI compress 3–5x this way."""
	try:
		from PIL import Image
	except ImportError:
		return
	img = Image.open(path).convert("RGB")
	img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
		path, optimize=True
	)


def main() -> int:
	env = env_file()
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument(
		"--url", default=os.environ.get("RD_URL") or f"http://localhost:{env.get('HTTP_PORT', '8080')}"
	)
	ap.add_argument("--user", default=os.environ.get("RD_USER", "Administrator"))
	ap.add_argument("--password", default=os.environ.get("RD_PASSWORD") or env.get("ADMIN_PASSWORD", "admin"))
	ap.add_argument(
		"--query",
		default=os.environ.get("RD_QUERY", "history"),
		help="a search that finds books in your catalogue (default: history)",
	)
	ap.add_argument("--theme", choices=["light", "dark"], default="light")
	ap.add_argument("--out", default=str(OUT), help="where the pictures go (default: the guides' own folder)")
	ap.add_argument("only", nargs="*", help=f"only these pictures: {', '.join(SHOTS)}")
	args = ap.parse_args()
	try:
		import playwright  # noqa: F401
	except ImportError:
		print(
			"Needs Playwright: pip install playwright && python3 -m playwright install chromium",
			file=sys.stderr,
		)
		return 1
	print(f"Taking screenshots of {args.url} into {args.out}/")
	done = asyncio.run(take(args))
	if Path(args.out).resolve() != OUT.resolve():
		record_taken(Path(args.out), done)
	wanted = len(args.only or SHOTS)
	print(f"{len(done)} of {wanted} taken.")
	return 0 if len(done) == wanted else 1


if __name__ == "__main__":
	sys.exit(main())
