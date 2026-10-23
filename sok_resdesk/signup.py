"""Join the portal from one short page: name, email and a password, and you are in.

Frappe's own sign-up sends an email whose link sets the password, so a reader whose email is late, in
spam or mistyped could not get in at all. Here the reader chooses the password at once and is signed in;
nothing waits on email. What the library chose still holds: *Anyone can sign up* gives the Reader role,
*Sign up, admin approves* leaves the account as a visitor with a request for a librarian, and *Admins add
readers* has no page.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from sok_resdesk import access
from sok_resdesk.core import access as core
from sok_resdesk.core import signup as rules
from sok_resdesk.ratelimit import rate_limit

MAX_PER_HOUR = 100  # all visitors together; Frappe's own sign-up has the same kind of cap


def open_to_join() -> bool:
	return access.signup_mode() != core.SIGNUP_CLOSED


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=6, seconds=3600)
def join(full_name: str = "", email: str = "", password: str = "", rd_hp: str = "") -> dict:
	"""Make the account, sign it in, and say where to go next. `rd_hp` is a field people cannot see."""
	if not open_to_join():
		frappe.throw(_("This library adds its readers itself. Please ask the library for an account."))
	# a form on another site can post forms and plain text but not JSON, so this cannot be done to a visitor
	# from elsewhere (it would sign them in to the attacker's account)
	if frappe.request and not (frappe.request.content_type or "").startswith("application/json"):
		frappe.throw(_("Please use the sign-up page."))
	fields, why = rules.clean(full_name, email, password, rd_hp)
	if why == "trap":
		return {"joined": 1, "status": "member"}  # looks like success to a robot, and nothing is made
	messages = {
		"name": _("Please give your name."),
		"email": _("That email address does not look right."),
		"password": _("Please choose a password of at least {0} characters.").format(rules.MIN_PASSWORD),
	}
	if why:
		frappe.throw(messages[why])
	if frappe.db.exists("User", {"email": fields["email"]}):
		frappe.throw(
			_("This email already has an account. Log in, or choose Forgot password on the login page.")
		)
	max_per_hour = cint(frappe.get_system_settings("max_signups_allowed_per_hour") or MAX_PER_HOUR)
	if frappe.db.get_creation_count("User", 60) >= min(max_per_hour, MAX_PER_HOUR):
		frappe.throw(_("Many people are joining just now. Please try again in an hour."))
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": fields["email"],
			"first_name": fields["full_name"],
			"enabled": 1,
			"new_password": fields["password"],
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	)
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	try:
		user.insert()  # access.on_user_insert files the request when a librarian must approve
	except frappe.DuplicateEntryError:  # two posts for one address at the same moment
		frappe.throw(
			_("This email already has an account. Log in, or choose Forgot password on the login page.")
		)
	mode = access.signup_mode()
	if mode == core.SIGNUP_OPEN:
		user.add_roles(access.READER_ROLE)
	frappe.db.commit()
	login = getattr(frappe.local, "login_manager", None)  # none outside a web request (tests)
	if login:
		login.login_as(user.name)
	return {"joined": 1, "status": "member" if mode == core.SIGNUP_OPEN else "pending"}
