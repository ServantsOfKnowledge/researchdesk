"""In-app help: the docs/*.md files shown on the portal (/library/help) and in the Desk
(/app/resdesk-help), plus the "Help" and "Take the tour" buttons on forms.

Everything is read from the Markdown in docs/, so updating a doc updates the help.
"""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe import _

from sok_resdesk.core import helpdocs

STAFF = ("System Manager", "ResDesk Manager", "ResDesk Cataloguer")

# The help section each Desk screen opens ("Help" button), as (page slug, heading anchor).
# tests/test_docs.py checks that every page and anchor here exists.
SCREEN_HELP = {
	"RD Item": ("collections-and-metadata", "editing-catalogue-details"),
	"RD Collection": ("collections-and-metadata", "curated-collections"),
	"RD Ingest Profile": ("ingesting", "ingest-profiles"),
	"RD Ingest Run": ("ingesting", "watching-pausing-and-stopping-runs"),
	"RD Settings": ("staff-guide", "settings"),
	"RD About Page": ("staff-guide", "the-about-page"),
	"RD Export": ("collections-and-metadata", "exporting-metadata"),
	"RD Metadata Import": ("collections-and-metadata", "editing-many-books-with-a-spreadsheet"),
	"RD Push Target": ("collections-and-metadata", "pushing-metadata-to-other-systems"),
	"RD Deposit": ("deposit", "reviewing"),
	"RD Archival Unit": ("archival-description", "describing"),
	"RD Contributor Release": ("staff-guide", "sharing-ground-truth"),
	"RD Wikimedia Account": ("wikimedia", "connect-your-account"),
	"RD Archive Account": ("archive-upload", "connect-your-account"),
	"RD Push Run": ("collections-and-metadata", "pushing-metadata-to-other-systems"),
	"RD External Record": ("collections-and-metadata", "pushing-metadata-to-other-systems"),
	"RD Reader Request": ("sign-in-email", "who-may-sign-up"),
	"RD Reader Profile": ("staff-guide", "reader-profiles-and-volunteers"),
	"RD Creator": ("staff-guide", "authors-and-subjects"),
	"RD Subject": ("staff-guide", "authors-and-subjects"),
	"resdesk-jobs": ("operations", "background-jobs-see-pause-and-stop-what-is-running"),
	"resdesk-server": ("server", "the-server-page"),
	"resdesk-people": ("staff-guide", "people-and-roles"),
	"resdesk-connections": ("connections", "the-kinds"),
	"resdesk-translations": ("staff-guide", "the-portal-in-other-languages"),
	"resdesk-authorities": ("staff-guide", "authors-and-subjects"),
	"resdesk-review": ("staff-guide", "the-review-queue"),
	"RD Review Flag": ("staff-guide", "the-review-queue"),
	"RD Library System": ("koha", "option-e-bring-the-librarys-catalogue-in-link-it-send-the-links-back"),
	"RD Library Record": ("koha", "option-e-bring-the-librarys-catalogue-in-link-it-send-the-links-back"),
	"RD Server Task": ("server", "upgrading-from-the-desk"),
	"RD Tombstone": ("preservation", "tombstones"),
	"RD Annotation": ("staff-guide", "readers-notes"),
	"RD Research Group": ("staff-guide", "readers-notes"),
	"RD Page Text": ("staff-guide", "proofreading-and-re-ocr"),
	"RD Ground Truth": ("staff-guide", "sharing-ground-truth"),
	"RD Preservation Event": ("preservation", "preservation-events"),
	"research-desk": ("staff-guide", "the-research-desk-workspace"),
}

# Portal help pages link to other portal pages; the rest go to the Desk help or GitHub.
PORTAL = "/library/help"
DESK = "/app/resdesk-help"


def _path(page: helpdocs.Page) -> Path:
	return helpdocs.docs_dir(Path(frappe.get_app_path("sok_resdesk"))) / page.file


SITE_PICTURES = "resdesk-guide"  # the site's own pictures (./resdesk.sh screenshots --site)
TAKEN = "taken.json"  # beside them: which shipped picture each one stood in for


def _shipped(name: str) -> Path:
	return Path(frappe.get_app_path("sok_resdesk", "public", "images", "guide", name))


def site_pictures() -> dict[str, str]:
	"""This library's own pictures that are still current, {name: url}. A picture retaken on the
	site (Server page → Retake help pictures) stands in for the one that comes with Research Desk
	only until an upgrade changes that one: then the screen it shows has changed, and the new
	shipped picture is truer than the library's old one. Pictures retaken before this was recorded
	count as old; a picture Research Desk doesn't ship is always the library's own."""
	import hashlib
	import json
	import os

	from sok_resdesk import __version__

	folder = Path(frappe.get_site_path("public", "files", SITE_PICTURES))
	marker = folder / TAKEN
	try:
		stamp = os.stat(folder).st_mtime_ns
	except OSError:
		return {}
	try:
		stamp = f"{stamp}-{os.stat(marker).st_mtime_ns}"
	except OSError:
		pass

	def current() -> dict[str, str]:
		try:
			taken = json.loads(marker.read_text())
		except (OSError, ValueError):
			taken = {}
		out = {}
		for mine in folder.glob("*.png"):
			name = mine.name
			try:
				shipped = hashlib.sha256(_shipped(name).read_bytes()).hexdigest()
			except OSError:
				shipped = None  # a picture only this library has
			if shipped is None or taken.get(name) == shipped:
				out[name] = f"/files/{SITE_PICTURES}/{name}?v={int(os.path.getmtime(mine))}"
		return out

	return frappe.cache.get_value(f"resdesk:site-pictures:{__version__}:{stamp}", current) or {}


def outdated_site_pictures() -> int:
	"""How many of this library's own pictures an upgrade has made out of date (the Server page)."""
	try:
		folder = Path(frappe.get_site_path("public", "files", SITE_PICTURES))
		mine = {p.name for p in folder.glob("*.png")}
	except OSError:
		return 0
	return len(mine - set(site_pictures()))


def image_url(name: str) -> str:
	"""A guide picture: this library's own when it is still current (above), else the one that
	comes with Research Desk, its address carrying the version so browsers fetch it anew after an
	upgrade instead of showing the one they kept."""
	from sok_resdesk import __version__

	try:
		mine = site_pictures().get(name)
		if mine:
			return mine
	except Exception:
		pass
	return f"{helpdocs.IMAGE_URL}/{name}?v={__version__}"


def _render(page: helpdocs.Page, where: str) -> dict:
	import markdown2

	md = _path(page).read_text(encoding="utf-8")

	def page_url(target, anchor):
		frag = f"#{anchor}" if anchor else ""
		if where == "portal":
			return f"{PORTAL}/{target.slug}{frag}" if target.audience == "reader" else None
		return f"{DESK}/{target.slug}{frag}"

	body = helpdocs.rewrite(md, page_url, image_url)
	html = markdown2.markdown(
		body,
		extras={
			"fenced-code-blocks": None,
			"tables": None,
			"html-classes": {"table": "table table-bordered", "img": "rd-help-img"},
		},
	)
	html = helpdocs.add_heading_ids(html, body)
	toc = [
		{"level": lvl, "text": text, "anchor": a} for lvl, text, a in helpdocs.headings(md) if lvl in (2, 3)
	]
	return {"slug": page.slug, "title": _(page.title), "html": html, "toc": toc}


def _index(audience: str | None = None) -> list[dict]:
	groups: dict[str, list] = {}
	for p in helpdocs.PAGES:
		if audience and p.audience != audience:
			continue
		groups.setdefault(p.group, []).append({"slug": p.slug, "title": _(p.title)})
	return [{"group": _(g), "pages": pages} for g, pages in groups.items()]


# the logo the help pages carry when the library hasn't set its own (Settings → Logo & Branding):
# the Servants of Knowledge logo, shipped with the app
HELP_LOGO = "/assets/sok_resdesk/images/sok-logo.png"


def brand() -> dict:
	"""The logo and name at the top of the help pages: the library's own (Settings → Logo), else the
	Servants of Knowledge logo that ships with Research Desk."""
	return {
		"logo": frappe.db.get_single_value("RD Settings", "portal_logo") or HELP_LOGO,
		"title": frappe.db.get_single_value("RD Settings", "portal_title") or "SOK Research Desk",
	}


def portal_page(slug: str | None) -> dict:
	"""For www/library/help.py: reader pages only."""
	page = helpdocs.BY_SLUG.get(slug or "reader-guide")
	if not page or page.audience != "reader":
		raise frappe.DoesNotExistError
	return {**_render(page, "portal"), "index": _index("reader"), "brand": brand()}


@frappe.whitelist()
def get_page(slug: str = "staff-guide") -> dict:
	"""For the Desk help page."""
	frappe.only_for(STAFF)
	from sok_resdesk.guide import mark_visited

	mark_visited("guide")
	page = helpdocs.BY_SLUG.get(slug)
	if not page:
		frappe.throw(_("No help page called {0}.").format(slug), frappe.DoesNotExistError)
	return {**_render(page, "desk"), "index": _index(), "brand": brand()}


def boot_session(bootinfo):
	"""The library's logo for the Desk sidebar; where each Help button goes; which screens have a tour."""
	from sok_resdesk.resdesk.doctype.rd_settings.rd_settings import DEFAULT_LOGO

	# a square picture suits the Desk's small icons best: the browser-tab icon, then the logo
	logo = (
		frappe.db.get_single_value("RD Settings", "favicon")
		or frappe.db.get_single_value("RD Settings", "portal_logo")
		or DEFAULT_LOGO
	)
	bootinfo.resdesk_brand = {
		"logo": logo,
		"title": frappe.db.get_single_value("RD Settings", "portal_title") or "",
	}
	if not any(r in frappe.get_roles() for r in STAFF):
		return
	from sok_resdesk.guide import TOURS

	bootinfo.resdesk_help = {
		"screens": {k: f"{DESK}/{slug}#{anchor}" for k, (slug, anchor) in SCREEN_HELP.items()},
		"tours": sorted(TOURS),
	}
