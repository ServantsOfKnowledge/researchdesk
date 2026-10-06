"""0.66.4: Creative Commons licence URLs become badges."""

import os

from sok_resdesk.core import licence as lic


def test_urls_become_licences():
	by_sa = lic.parse("https://creativecommons.org/licenses/by-sa/4.0/")
	assert (by_sa.label, by_sa.code) == ("CC BY-SA 4.0", "by-sa-4.0")
	assert by_sa.name == "Attribution-ShareAlike 4.0 International"
	assert by_sa.badge.endswith("/by-sa-4.0.svg")
	assert lic.parse("http://creativecommons.org/licenses/by-nc-nd/3.0/deed.en").code == "by-nc-nd-3.0"
	assert lic.parse("https://creativecommons.org/publicdomain/zero/1.0/").label == "CC0 1.0"
	assert lic.parse("https://creativecommons.org/publicdomain/mark/1.0/").label == "Public Domain Mark"


def test_other_licences_and_blanks_stay_plain_links():
	assert lic.parse("https://example.org/our-licence") is None
	assert lic.parse("") is None and lic.parse(None) is None


def test_every_badge_the_licences_can_point_at_exists():
	folder = os.path.join(os.path.dirname(__file__), "..", "public", "images", "licences")
	for code in lic.all_codes():
		assert os.path.isfile(os.path.join(folder, f"{code}.svg")), code
	for url in (
		"https://creativecommons.org/licenses/by/4.0/",
		"https://creativecommons.org/licenses/by-nc-sa/4.0/",
		"https://creativecommons.org/licenses/by-nd/3.0/",
	):
		assert os.path.isfile(os.path.join(folder, os.path.basename(lic.parse(url).badge)))
