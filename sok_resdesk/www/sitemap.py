"""/sitemap.xml: an index of the portal's pages and every published public book, in parts
(/sitemap.xml?part=1…). Takes the place of Frappe's, which doesn't know the books."""

import frappe

from sok_resdesk.seo import sitemap

base_template_path = "www/sitemap.xml"
no_cache = 1


def get_context(context):
	part = frappe.form_dict.get("part") or 0
	return {"xml": sitemap(part if part == "pages" else frappe.utils.cint(part))}
