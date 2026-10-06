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
		record["downloads"] = []
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
	# a manuscript has its leaves beside a place to transcribe them, even before any text exists
	media = record.get("media")
	context.page_reader = not media and bool(
		record.get("has_page_text")
		or record.get("on_archive_org")
		or record.get("item_type") == "Manuscript"
		or record.get("local_images")
	)
	# a book of photographs (a manuscript, a photograph) is read in Page & text: it has no PDF to show
	own_images = bool(record.get("local_images"))
	wanted = frappe.form_dict.get("view") or ("text" if own_images and not record.get("pdf_url") else "")
	# Page & text and the text downloads are for members (bandwidth, scraping); guests see why
	context.text_reader = context.page_reader and access.can_use_text(record.get("visibility"))
	context.members_note = context.page_reader and context.can_read and not context.text_reader
	context.start_view = "text" if context.text_reader and wanted == "text" else "book"
	# Reader: the Internet Archive's BookReader when the book is there, the PDF from our own files,
	# or for a repository's book its record and PDF there (other sites' PDFs often refuse a frame)
	context.reader = (
		"media"
		if media
		else "ia"
		if record.get("on_archive_org")
		else "remote"
		if record.get("from_repository") or record.get("from_wikisource")
		else ("pdf" if record.get("pdf_url") else "none")
	)
	context.pdf_url = record.get("pdf_url") or ""
	context.q = frappe.form_dict.get("q") or ""
	context.portal_url = f"{root}/library/item/{item_id}"
	from sok_resdesk import features, iiif

	# the book as a IIIF manifest, for viewers such as Mirador (Settings → Features → Sharing)
	context.iiif_url = (
		f"{root}/iiif/{item_id}/manifest"
		if context.can_read
		and features.on("sharing")
		and record.get("page_count")
		and (record.get("on_archive_org") or record.get("from_wikisource") or iiif.drawn_here(record))
		else ""
	)
	context.formats = [(k, v[0]) for k, v in citations.FORMATS.items()]
	context.cites = {k: citations.render(record, k, root) for k in citations.FORMATS}
	context.highwire = citations.highwire_tags(record, root)
	context.json_ld = json.dumps(citations.json_ld(record, root), ensure_ascii=False)
	context.coins = citations.coins(record, root)
	from sok_resdesk.core.seo import describe
	from sok_resdesk.librarysystems import catalogue_links

	try:
		from sok_resdesk import archival

		context.archival_trail = archival.item_trail(record["item_id"])
	except Exception:
		context.archival_trail = []
	try:
		context.catalogue_links = catalogue_links(record["item_id"])  # the libraries' own records of it
	except Exception:
		context.catalogue_links = []

	context.metatags = {
		"title": context.title,
		"description": describe(record, context.portal_title),  # search results and link previews
		"image": record.get("thumbnail_url"),
		"og:type": "book",
	}
	return context
