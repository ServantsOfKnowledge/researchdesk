import json

import frappe
from frappe.utils import cint

from sok_resdesk import access
from sok_resdesk.catalogue import base_url, get_record, settings
from sok_resdesk.core import citations

no_cache = 1


def get_context(context):
	access.require_login_for_portal()
	item_id = frappe.form_dict.get("item_id")
	record = get_record(item_id) if item_id else None
	if not record:
		# a members-only book: guests are asked to log in rather than told it doesn't exist
		if (
			frappe.session.user == "Guest"
			and item_id
			and frappe.db.exists("RD Item", {"name": item_id, "published": 1})
		):
			frappe.local.flags.redirect_location = access.login_url(f"/library/item/{item_id}")
			raise frappe.Redirect
		raise frappe.PageDoesNotExistError

	root = base_url()
	s = settings()
	context.no_cache = 1
	context.full_width = 1
	context.show_sidebar = 0
	context.portal_title = s.portal_title or "SOK Research Desk"
	context.can_read = access.can_read(record.get("visibility"))
	if not context.can_read:
		record["pdf_url"] = ""  # keep it out of the page and its citation meta tags
	context.item = record
	context.viewer = access.viewer()
	names = record.get("curated_collections") or []
	context.curated = (
		frappe.get_all(
			"RD Collection",
			filters={"name": ("in", names), "published": 1},
			fields=["name", "title"],
			order_by="title",
		)
		if names
		else []
	)
	context.login_url = access.login_url(f"/library/item/{item_id}")
	context.title = citations.display_title(record)
	context.start_leaf = max(0, cint(frappe.form_dict.get("page")))
	# two readers side by side: the book reader (archive.org's, as before) and the page reader
	# (page image and its text, page links and page citations); ?view=text opens the second
	context.page_reader = bool(record.get("has_page_text") or record.get("on_archive_org"))
	context.start_view = "text" if context.page_reader and frappe.form_dict.get("view") == "text" else "book"
	# Reader: the Internet Archive's BookReader when the book is there, the PDF from our own files,
	# or for a repository's book its record and PDF there (other sites' PDFs often refuse a frame)
	context.reader = (
		"ia"
		if record.get("on_archive_org")
		else "remote"
		if record.get("from_repository")
		else ("pdf" if record.get("pdf_url") else "none")
	)
	context.pdf_url = record.get("pdf_url") or ""
	context.q = frappe.form_dict.get("q") or ""
	context.portal_url = f"{root}/library/item/{item_id}"
	context.formats = [(k, v[0]) for k, v in citations.FORMATS.items()]
	context.cites = {k: citations.render(record, k, root) for k in citations.FORMATS}
	context.highwire = citations.highwire_tags(record, root)
	context.json_ld = json.dumps(citations.json_ld(record, root), ensure_ascii=False)
	context.coins = citations.coins(record, root)
	context.metatags = {
		"title": context.title,
		"description": (record.get("description") or "")[:300],
		"image": record.get("thumbnail_url"),
	}
	return context
