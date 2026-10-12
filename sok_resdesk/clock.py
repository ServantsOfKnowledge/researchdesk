"""Date, time and sign-in links, managed from the Server page.

Frappe keeps every stored time in the System Settings time zone, and a link in a welcome or
password-reset email lives for the System Settings link lifetime from the moment the email is
*made*, not the moment it arrives. So a link arrives expired when the email waited in the queue
(outgoing email not working, retries) or the lifetime is short. This shows the clock, the
lifetime and the waiting emails together, changes the first two, and sends a fresh link."""

from datetime import UTC, datetime

import frappe
from frappe import _
from frappe.utils import cint, get_system_timezone, now_datetime

from sok_resdesk import access
from sok_resdesk.core import clock as core

LIFETIME = "reset_password_link_expiry_duration"  # seconds, in System Settings
PROTECTED = ("Administrator", "Guest")
FRAPPE_DEFAULT = 1200  # Frappe ships a 20 minute link life: too short for email that is read later
KINDER = 24 * 3600


def _lifetime() -> int | None:
	if not frappe.get_meta("System Settings").has_field(LIFETIME):
		return None
	return cint(frappe.db.get_single_value("System Settings", LIFETIME))


def _oldest_mail_wait() -> tuple[int, int]:
	"""(emails waiting or failed, seconds the oldest has waited)."""
	rows = frappe.db.sql(
		"select count(*), min(creation) from `tabEmail Queue` where status in ('Not Sent','Partially Sent','Error')"
	)
	count, oldest = rows[0] if rows else (0, None)
	wait = int((now_datetime() - oldest).total_seconds()) if oldest else 0
	return cint(count), max(wait, 0)


def status() -> dict:
	zone = get_system_timezone()
	waiting, wait = _oldest_mail_wait()
	expiry = _lifetime()
	host = datetime.now().astimezone().utcoffset().total_seconds()
	return {
		"time_zone": zone,
		"now": str(now_datetime())[:19],
		"utc": str(datetime.now(UTC).replace(tzinfo=None))[:19],
		"host_zone": datetime.now().astimezone().tzname(),
		"lifetime_hours": round(expiry / 3600, 1) if expiry else (0 if expiry == 0 else None),
		"mail_waiting": waiting,
		"mail_wait_minutes": wait // 60,
		"advice": core.advise(expiry, wait, int(host), core.offset_seconds(zone)),
	}


@frappe.whitelist(methods=["POST"])
def set_clock(time_zone: str = "", lifetime_hours: float = 0) -> dict:
	"""Administrators: the System Settings time zone and how long a mailed link lives."""
	frappe.only_for(access.SUPER_ROLES)
	if time_zone:
		if time_zone not in core.zone_names():
			frappe.throw(_("{0} is not a time zone name (for example Asia/Kolkata).").format(time_zone))
		frappe.db.set_single_value("System Settings", "time_zone", time_zone)
	hours = float(lifetime_hours or 0)
	if hours:
		if not 1 <= hours <= 24 * 30:
			frappe.throw(_("A link can live from 1 hour to 30 days."))
		if _lifetime() is None:
			frappe.throw(_("This version of Frappe has no link lifetime setting."))
		frappe.db.set_single_value("System Settings", LIFETIME, int(hours * 3600))
	frappe.clear_cache()
	return {"message": _("Saved."), **status()}


@frappe.whitelist(methods=["POST"])
def send_new_link(user: str) -> dict:
	"""Managers: a fresh password link for one account, made now and mailed now."""
	frappe.only_for((*access.MANAGER_ROLES, access.SUPER_ROLE))
	user = (user or "").strip().lower()
	if user in PROTECTED or not frappe.db.exists("User", user):
		frappe.throw(_("There is no such account."))
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(_("{0} is switched off.").format(user))
	doc = frappe.get_doc("User", user)
	doc.validate_reset_password()
	doc._reset_password(send_email=True)  # the call Frappe's own "forgot password" makes
	return {"message": _("A new link was made and queued for {0}. It lives from now.").format(user)}


def lengthen_default() -> bool:
	"""Install and upgrade: a link life still at Frappe's 20 minutes becomes 24 hours, once. Anything
	an administrator chose (including "no limit") is left alone."""
	if _lifetime() != FRAPPE_DEFAULT:
		return False
	frappe.db.set_single_value("System Settings", LIFETIME, KINDER)
	return True
