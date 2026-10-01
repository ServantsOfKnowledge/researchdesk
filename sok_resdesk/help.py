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
	"RD Push Run": ("collections-and-metadata", "pushing-metadata-to-other-systems"),
	"RD External Record": ("collections-and-metadata", "pushing-metadata-to-other-systems"),
	"RD Reader Request": ("access", "reader-accounts"),
	"RD Creator": ("staff-guide", "authors-and-subjects"),
	"RD Subject": ("staff-guide", "authors-and-subjects"),
	"resdesk-jobs": ("operations", "background-jobs-see-pause-and-stop-what-is-running"),
	"resdesk-server": ("server", "the-server-page"),
	"RD Server Task": ("server", "upgrading-from-the-desk"),
	"research-desk": ("staff-guide", "the-research-desk-workspace"),
}

# Portal help pages link to other portal pages; the rest go to the Desk help or GitHub.
PORTAL = "/library/help"
DESK = "/app/resdesk-help"


def _path(page: helpdocs.Page) -> Path:
	return helpdocs.docs_dir(Path(frappe.get_app_path("sok_resdesk"))) / page.file


def _render(page: helpdocs.Page, where: str) -> dict:
	import markdown2

	md = _path(page).read_text(encoding="utf-8")

	def page_url(target, anchor):
		frag = f"#{anchor}" if anchor else ""
		if where == "portal":
			return f"{PORTAL}/{target.slug}{frag}" if target.audience == "reader" else None
		return f"{DESK}/{target.slug}{frag}"

	body = helpdocs.rewrite(md, page_url)
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


def portal_page(slug: str | None) -> dict:
	"""For www/library/help.py: reader pages only."""
	page = helpdocs.BY_SLUG.get(slug or "reader-guide")
	if not page or page.audience != "reader":
		raise frappe.DoesNotExistError
	return {**_render(page, "portal"), "index": _index("reader")}


@frappe.whitelist()
def get_page(slug: str = "staff-guide") -> dict:
	"""For the Desk help page."""
	frappe.only_for(STAFF)
	from sok_resdesk.guide import mark_visited

	mark_visited("guide")
	page = helpdocs.BY_SLUG.get(slug)
	if not page:
		frappe.throw(_("No help page called {0}.").format(slug), frappe.DoesNotExistError)
	return {**_render(page, "desk"), "index": _index()}


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
