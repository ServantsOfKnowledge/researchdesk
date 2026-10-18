"""0.82: directory sign-in rules and the leaver check."""

import frappe
from frappe.tests import IntegrationTestCase

from sok_resdesk import directory


def ldap(**values):
	base = {
		"enabled": 1,
		"ldap_server_url": "ldaps://dir.example.gov",
		"ssl_tls_mode": "Off",
		"require_trusted_certificate": "Yes",
		"ldap_groups": [],
		"default_role": None,
	}
	return frappe._dict({**base, **values})


class TestDirectory(IntegrationTestCase):
	USER = "rddirtest@example.com"

	def setUp(self):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.USER,
				"first_name": "Dir",
				"username": "rddirtest",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(self._clean)

	def _clean(self):
		frappe.set_user("Administrator")
		frappe.form_dict.pop("cmd", None)
		frappe.db.delete(directory.ACCOUNT, {"user": self.USER})
		frappe.delete_doc("User", self.USER, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_a_secure_ldap_setup_passes(self):
		directory.check_ldap(ldap())

	def test_ldap_in_the_clear_or_with_an_unchecked_certificate_is_refused(self):
		for bad in (
			ldap(ldap_server_url="ldap://dir.example.gov"),
			ldap(require_trusted_certificate="No"),
		):
			with self.assertRaises(frappe.ValidationError):
				directory.check_ldap(bad)
		directory.check_ldap(ldap(ldap_server_url="ldap://dir.example.gov", ssl_tls_mode="StartTLS"))

	def test_a_disabled_ldap_is_not_checked(self):
		directory.check_ldap(ldap(enabled=0, ldap_server_url="ldap://x"))

	def test_a_directory_group_cannot_be_mapped_to_a_governance_duty(self):
		for role in ("ResDesk Records Officer", "ResDesk Security Officer", "System Manager"):
			with self.assertRaises(frappe.ValidationError):
				directory.check_ldap(ldap(ldap_groups=[frappe._dict(erpnext_role=role)]))
		directory.check_ldap(ldap(ldap_groups=[frappe._dict(erpnext_role="ResDesk Reader")]))
		with self.assertRaises(frappe.ValidationError):
			directory.check_ldap(ldap(default_role="System Manager"))

	def test_a_provider_on_plain_http_or_trusting_emails_is_refused(self):
		ok = frappe._dict(enable_social_login=1, authorize_url="https://sso.example.gov/auth")
		directory.check_social_key(ok)
		for bad in (
			frappe._dict(enable_social_login=1, authorize_url="http://sso.example.gov/auth"),
			frappe._dict(enable_social_login=1, trust_email_without_verified_claim=1),
		):
			with self.assertRaises(frappe.ValidationError):
				directory.check_social_key(bad)

	def test_a_directory_sign_in_is_noted(self):
		frappe.set_user(self.USER)
		frappe.form_dict.cmd = "frappe.integrations.doctype.ldap_settings.ldap_settings.login"
		directory.on_login()
		assert frappe.db.get_value(directory.ACCOUNT, self.USER, "source") == "LDAP"

	def test_an_ordinary_sign_in_is_not_a_directory_one(self):
		frappe.set_user(self.USER)
		frappe.form_dict.cmd = "login"
		directory.on_login()
		assert not frappe.db.exists(directory.ACCOUNT, self.USER)

	def test_a_role_in_another_case_is_still_refused(self):
		with self.assertRaises(frappe.ValidationError):
			directory.check_ldap(ldap(ldap_groups=[frappe._dict(erpnext_role="system manager")]))

	def test_a_directory_sign_in_into_an_officers_account_is_refused(self):
		frappe.get_doc("User", self.USER).add_roles("System Manager")
		frappe.set_user(self.USER)
		frappe.form_dict.cmd = "frappe.integrations.doctype.ldap_settings.ldap_settings.login"
		with self.assertRaises(frappe.PermissionError):
			directory.on_login()

	def test_an_ldap_account_stays_ldap_when_it_also_signs_in_by_sso(self):
		frappe.get_doc({"doctype": directory.ACCOUNT, "user": self.USER, "source": "LDAP"}).insert(
			ignore_permissions=True
		)
		frappe.set_user(self.USER)
		frappe.form_dict.cmd = "frappe.integrations.oauth2_logins.custom"
		directory.on_login()
		assert frappe.db.get_value(directory.ACCOUNT, self.USER, "source") == "LDAP"

	def test_a_leaver_is_switched_off_and_the_administrator_never_is(self):
		frappe.get_doc({"doctype": directory.ACCOUNT, "user": self.USER, "source": "LDAP"}).insert(
			ignore_permissions=True
		)
		assert directory._switch_off(self.USER, "test")
		assert not frappe.db.get_value("User", self.USER, "enabled")
		assert frappe.db.get_value(directory.ACCOUNT, self.USER, "disabled_on")
		assert not directory._switch_off("Administrator", "test")
		assert frappe.db.get_value("User", "Administrator", "enabled")
