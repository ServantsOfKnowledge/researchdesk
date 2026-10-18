from sok_resdesk_governance.core.directory import (
	https_or_local,
	ldap_connection_problems,
	missing_after,
	privileged_mapped,
	to_switch_off,
	too_many,
)


def test_a_directory_cannot_hand_out_the_governance_duties():
	assert privileged_mapped(["ResDesk Reader", "ResDesk Records Officer", "System Manager"]) == [
		"ResDesk Records Officer",
		"System Manager",
	]
	assert privileged_mapped(["ResDesk Reader", "ResDesk Manager"]) == []


def test_the_site_configuration_can_allow_a_duty():
	assert privileged_mapped(["ResDesk Records Officer"], allowed=["ResDesk Records Officer"]) == []


def test_ldap_must_be_encrypted_and_the_certificate_checked():
	assert ldap_connection_problems("ldaps://dir.example.gov", "Off", "Yes") == []
	assert ldap_connection_problems("ldap://dir.example.gov", "StartTLS", "Yes") == []
	assert len(ldap_connection_problems("ldap://dir.example.gov", "Off", "Yes")) == 1
	assert len(ldap_connection_problems("ldaps://dir.example.gov", "Off", "No")) == 1
	assert len(ldap_connection_problems("", "Off", "No")) == 2


def test_sso_addresses_must_be_https_except_on_this_machine():
	assert https_or_local("https://sso.example.gov/authorize")
	assert https_or_local("http://localhost:8080/auth")
	assert not https_or_local("http://sso.example.gov/authorize")
	assert not https_or_local("")


def test_a_leaver_is_switched_off_only_after_two_misses_in_a_row():
	n = missing_after(0, False)
	assert not to_switch_off(n)
	n = missing_after(n, False)
	assert to_switch_off(n)
	assert missing_after(n, True) == 0  # found again: the count starts over


def test_a_role_spelt_in_another_case_is_still_refused():
	assert privileged_mapped(["system manager", " sok super admin "]) == ["SOK Super Admin", "System Manager"]
	assert privileged_mapped(["SYSTEM MANAGER"], allowed=["system manager"]) == []


def test_a_run_that_would_switch_off_a_fifth_of_everyone_stops():
	assert not too_many(2, 10)
	assert too_many(3, 10)
	assert not too_many(20, 100)
	assert too_many(21, 100)
