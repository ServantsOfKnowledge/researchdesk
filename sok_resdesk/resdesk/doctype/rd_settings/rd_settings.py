# Copyright (c) 2026, Servants of Knowledge and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document
from frappe.utils import escape_html


class RDSettings(Document):
	def validate(self):
		if self.base_url:
			self.base_url = self.base_url.rstrip("/")
		if self.index_prefix:
			self.index_prefix = frappe.scrub(self.index_prefix)

	def on_update(self):
		apply_branding(self)
		from sok_resdesk.access import apply_signup_setting

		apply_signup_setting(self)


def apply_branding(settings=None):
	"""Push the portal name and logo to Frappe's website navbar, favicon and Desk logo."""
	s = settings or frappe.get_single("RD Settings")
	title = s.portal_title or "SoK Research Desk"
	logo = s.portal_logo or ""

	ws = frappe.get_single("Website Settings")
	ws.app_name = title
	if logo:
		label = f'<span class="rd-brand__name">{escape_html(title)}</span>' if s.show_title_in_navbar else ""
		ws.brand_html = (
			f'<span class="rd-brand"><img src="{escape_html(logo)}" alt="{escape_html(title)}" '
			f'class="rd-brand__logo">{label}</span>'
		)
		ws.app_logo = logo
	else:
		ws.brand_html = escape_html(title)
		ws.app_logo = None
	ws.favicon = s.favicon or logo or ws.favicon
	ws.flags.ignore_permissions = True
	ws.save()

	if frappe.db.exists("DocType", "Navbar Settings"):
		nav = frappe.get_single("Navbar Settings")
		nav.app_logo = logo or None
		nav.flags.ignore_permissions = True
		nav.save()
	frappe.clear_cache()
