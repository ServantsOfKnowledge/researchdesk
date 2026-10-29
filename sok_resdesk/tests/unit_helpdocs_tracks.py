"""Help follows the role (core/helpdocs.py): every page has a track, and roles get the tracks they should."""

from sok_resdesk.core import helpdocs as h


def test_every_help_page_is_in_a_track_so_nothing_is_lost():
	listed = {slug for t in h.TRACKS for slug in t.pages}
	assert listed >= {p.slug for p in h.PAGES}, {p.slug for p in h.PAGES} - listed
	assert all(slug in h.BY_SLUG for slug in listed), "a track names a page that does not exist"


def test_each_track_begins_with_a_page_for_it():
	assert [t.pages[0] for t in h.TRACKS][:3] == ["reader-guide", "staff-guide", "ingesting"]


def test_roles_get_their_tracks_and_a_plain_account_the_reader_help():
	keys = lambda roles: [t.key for t in h.tracks_for(roles)]  # noqa: E731
	assert keys(["ResDesk Cataloguer"]) == ["everyone", "catalogue", "lending"]
	assert keys(["ResDesk Manager", "ResDesk Cataloguer"]) == ["everyone", "library", "catalogue", "lending"]
	assert keys(["System Manager"]) == list(h.EVERY_TRACK)
	assert keys(["Some Other Role"]) == keys([]) == ["everyone"]


def test_the_navigation_lists_a_page_once_and_in_the_viewers_words():
	nav = h.index_for(h.tracks_for(["ResDesk Manager"]), lambda t: t.upper())
	slugs = [p["slug"] for g in nav for p in g["pages"]]
	assert len(slugs) == len(set(slugs))
	assert (
		"lending" in slugs and "koha" in slugs and "api" not in slugs
	)  # technical pages stay out of a manager's list
	assert nav[0]["pages"][0] == {"slug": "reader-guide", "title": "USING THE LIBRARY"}
