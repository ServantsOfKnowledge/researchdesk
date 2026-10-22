import frappe
from frappe.utils import cint

from sok_resdesk import access, contact
from sok_resdesk.catalogue import settings

no_cache = 1


def get_context(context):
	"""Contact us: anyone, signed in or not, may write to the library."""
	access.require_login_for_portal()
	if not contact.enabled():
		raise frappe.PageDoesNotExistError
	s = settings()
	from sok_resdesk.translations import tr

	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = f"{frappe._('Contact us')} · {context.portal_title}"
	context.intro = tr(s.get("contact_intro") or "")
	days = s.get("contact_keep_days")
	context.keep_days = contact.KEEP_DAYS if days in (None, "") else cint(days)
	context.max_message = contact.rules.MAX_MESSAGE
	context.metatags = {"title": context.title, "description": frappe._("Write to the library")}
	return context
