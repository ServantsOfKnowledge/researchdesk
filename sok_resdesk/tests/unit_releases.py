"""0.60: which licences let a ground-truth set carry a contributor's pages."""

from sok_resdesk.core import groundtruth as gt


def test_a_set_may_be_as_strict_or_stricter_than_the_contributor_allows():
	assert (
		gt.allows("CC0-1.0", "CC0-1.0")
		and gt.allows("CC0-1.0", "CC-BY-4.0")
		and gt.allows("CC0-1.0", "CC-BY-SA-4.0")
	)
	assert gt.allows("CC-BY-4.0", "CC-BY-4.0") and gt.allows("CC-BY-4.0", "CC-BY-SA-4.0")
	assert not gt.allows("CC-BY-4.0", "CC0-1.0")
	assert gt.allows("CC-BY-SA-4.0", "CC-BY-SA-4.0")
	assert not gt.allows("CC-BY-SA-4.0", "CC-BY-4.0") and not gt.allows("CC-BY-SA-4.0", "CC0-1.0")


def test_no_release_or_no_set_licence_allows_nothing():
	assert (
		not gt.allows(None, "CC0-1.0") and not gt.allows("CC0-1.0", None) and not gt.allows("GPL", "CC0-1.0")
	)
