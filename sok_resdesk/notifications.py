"""Frappe's own notification emails, kept off.

Research Desk emails only account messages (welcome, password, sign-up). Frappe's notifications
(a mention, an assignment, a share, energy points, event reminders, emails on assigned documents)
stay in the Desk bell: hooks.py lists their types as never emailing, and this switches off each
person's master email setting, for the accounts there are and for every new one. A person who
wants those emails can turn the setting back on in their own Notification Settings."""

import frappe

SETTING = "enable_email_notifications"


def quiet(user: str) -> None:
	"""Email notifications off for one account (its Notification Settings made if Frappe has not)."""
	if user in ("Guest",):
		return
	from frappe.desk.doctype.notification_settings.notification_settings import create_notification_settings

	create_notification_settings(user)
	frappe.db.set_value("Notification Settings", user, SETTING, 0, update_modified=False)


def quiet_new_user(doc, method=None) -> None:
	"""User hook, after Frappe has made the account's Notification Settings."""
	quiet(doc.name)


def quiet_everyone() -> int:
	"""Upgrade: every enabled account, and any Email Digest paused. Returns how many accounts."""
	users = frappe.get_all("User", filters={"enabled": 1, "name": ("not in", ("Guest",))}, pluck="name")
	for user in users:
		quiet(user)
	if frappe.db.exists("DocType", "Email Digest"):
		frappe.db.sql("update `tabEmail Digest` set enabled = 0")
	return len(users)
