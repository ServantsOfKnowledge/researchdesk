"""Advice about mailed-link expiry and the test account list."""

from sok_resdesk.core.clock import DAY, advise, offset_seconds
from sok_resdesk.core.testaccounts import ACCOUNTS, DOMAIN, new_password


def test_frappes_twenty_minutes_is_called_short():
	assert "short" in advise(1200, 0, 0, 0)
	assert advise(DAY, 0, 0, 0) == []
	assert advise(0, 0, 0, 0) == []  # no limit set


def test_late_mail_is_named_and_one_that_outlives_its_link_too():
	assert advise(DAY, 700, 0, 0) == ["mail_late"]
	assert advise(1200, 1500, 0, 0) == ["short", "mail_late", "mail_outlives"]


def test_a_frappe_without_the_setting_and_a_differing_zone():
	assert advise(None, 0, 0, 0) == ["no_setting"]
	assert advise(DAY, 0, 3600, 19800) == ["zone_differs"]


def test_offset_of_a_named_zone():
	assert offset_seconds("Asia/Kolkata") == 19800
	assert offset_seconds("UTC") == 0


def test_test_accounts_are_unique_example_addresses_for_every_role():
	emails = [a.email for a in ACCOUNTS]
	assert len(set(emails)) == len(emails)
	assert all(e.endswith("@" + DOMAIN) for e in emails)
	roles = {r for a in ACCOUNTS for r in a.roles}
	assert roles == {
		"ResDesk Reader",
		"ResDesk Depositor",
		"ResDesk Proofreader",
		"ResDesk Cataloguer",
		"ResDesk Manager",
		"SOK Super Admin",
		"System Manager",
	}
	assert any(not a.enabled for a in ACCOUNTS) and any(not a.roles for a in ACCOUNTS)
	assert new_password() != new_password()
