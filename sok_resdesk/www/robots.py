"""/robots.txt: Research Desk's rules (seo.py), the library's own lines from Website Settings,
and the sitemap. Takes the place of Frappe's."""

from sok_resdesk.seo import robots

base_template_path = "www/robots.txt"
no_cache = 1


def get_context(context):
	return {"robots_txt": robots()}
