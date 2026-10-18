"""Classified mode: which outside hosts stay reachable (core/classified.py)."""

from sok_resdesk_governance.core.classified import host_allowed


def test_the_machine_itself_is_always_reachable():
	for h in ("localhost", "127.0.0.1", "::1", "LOCALHOST"):
		assert host_allowed(h, [])


def test_an_outside_host_is_refused_unless_named():
	assert not host_allowed("archive.org", [])
	assert not host_allowed("archive.org", ["wikidata.org"])
	assert host_allowed("meilisearch", ["meilisearch"])
	assert not host_allowed("", ["meilisearch"]) and not host_allowed(None, ["meilisearch"])


def test_a_trailing_dot_in_the_list_still_matches():
	assert host_allowed("meilisearch", ["meilisearch."])
	assert host_allowed("meilisearch.", ["meilisearch"])


def test_a_leading_dot_names_the_whole_domain_and_nothing_that_merely_ends_alike():
	assert host_allowed("ldap.dept.gov.example", [".gov.example"])
	assert host_allowed("gov.example", [".gov.example"])
	assert not host_allowed("evilgov.example", [".gov.example"])
	assert not host_allowed("gov.example.evil.org", [".gov.example"])
