import frappe

from sok_resdesk import access, signup
from sok_resdesk.catalogue import settings
from sok_resdesk.core import access as core
from sok_resdesk.core.signup import safe_next

no_cache = 1


def get_context(context):
	"""Join: name, email and a password, and you are in. The page is not there if the library adds its
	readers itself, and a signed-in person has nothing to do here."""
	if not signup.open_to_join():
		raise frappe.PageDoesNotExistError
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/library"
		raise frappe.Redirect
	s = settings()
	from sok_resdesk.translations import tr

	context.update({"no_cache": 1, "full_width": 1, "show_sidebar": 0})
	context.portal_title = tr(s.portal_title) or "SOK Research Desk"
	context.title = f"{frappe._('Create an account')} · {context.portal_title}"
	context.approval = access.signup_mode() == core.SIGNUP_APPROVE
	context.min_password = signup.rules.MIN_PASSWORD
	context.next_url = safe_next(frappe.form_dict.get("redirect-to"))
	context.login_url = access.login_url(context.next_url)
	context.metatags = {"title": context.title, "robots": "noindex"}
	return context
