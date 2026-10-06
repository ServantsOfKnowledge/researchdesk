"""0.66.1: the Connections catalogue: complete, consistent, and role-aware."""

from sok_resdesk.core import connections as c


def test_every_card_belongs_to_a_group_and_has_a_way_in():
	groups = {g.key for g in c.GROUPS}
	keys = [x.key for x in c.CARDS]
	assert len(keys) == len(set(keys))
	for x in c.CARDS:
		assert x.group in groups
		assert x.actions or x.urls, f"{x.key} gives no way in"
		assert x.who and x.what


def test_every_group_has_cards_and_the_main_integrations_are_there():
	for g in c.GROUPS:
		assert any(x.group == g.key for x in c.CARDS), g.key
	for key in ("ia_bring", "ia_send", "wm_account", "koha", "deposit", "calibre", "oai", "sru", "exports"):
		assert c.card(key)


def test_roles_decide_who_may_use_a_card():
	send = c.card("ia_send")
	assert c.can_use(send, {"ResDesk Depositor"})
	assert c.can_use(send, {"ResDesk Cataloguer"})
	assert not c.can_use(send, {"ResDesk Proofreader"})
	ingest = c.card("ia_bring")
	assert c.can_use(ingest, {"ResDesk Manager"}) and not c.can_use(ingest, {"ResDesk Cataloguer"})
	assert c.can_use(c.card("oai"), set())  # open standards are for everyone
