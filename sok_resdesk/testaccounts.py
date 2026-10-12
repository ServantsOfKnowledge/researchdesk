"""Create or remove the test accounts (docs/test-accounts.md): `bench resdesk test-accounts`."""

import frappe
from frappe.utils.password import update_password

from sok_resdesk.core.testaccounts import ACCOUNTS, new_password


def create(password: str | None = None) -> dict:
	"""Make (or reset) one account per kind of person, all with one password. No email is sent."""
	password = password or new_password()
	for a in ACCOUNTS:
		if frappe.db.exists("User", a.email):
			doc = frappe.get_doc("User", a.email)
			doc.enabled = 1 if a.enabled else 0
		else:
			doc = frappe.get_doc(
				{
					"doctype": "User",
					"email": a.email,
					"first_name": a.name,
					"enabled": 1 if a.enabled else 0,
					"user_type": "System User" if a.desk else "Website User",
					"send_welcome_email": 0,
				}
			)
		have = {r.role for r in doc.get("roles") or []}
		for role in a.roles:
			if role not in have:
				doc.append("roles", {"role": role})
		doc.flags.ignore_permissions = True
		doc.flags.no_welcome_mail = True
		doc.save() if doc.get("creation") else doc.insert()
		update_password(a.email, password)
	return {"password": password, "accounts": [a.email for a in ACCOUNTS]}


def remove() -> int:
	"""Delete the test accounts (and only those)."""
	gone = 0
	for a in ACCOUNTS:
		if frappe.db.exists("User", a.email):
			frappe.delete_doc("User", a.email, ignore_permissions=True, force=True)
			gone += 1
	return gone
