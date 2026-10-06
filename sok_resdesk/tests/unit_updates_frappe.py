"""0.66.3: a release names the Frappe it needs, and an upgrade brings Frappe with it."""

from sok_resdesk.core import updates as upd


def test_a_release_names_its_frappe():
	assert upd.frappe_min('__version__ = "0.66.3"\n__frappe_min__ = "16.50.0"\n') == "16.50.0"
	assert upd.frappe_min('__version__ = "0.66.3"\n') is None
	assert upd.frappe_min('__frappe_min__ = "soon"') is None
	assert upd.frappe_min(None) is None


def test_frappe_is_updated_with_the_app_only_when_it_is_too_old():
	assert upd.needs_frappe_update("16.50.0", "16.36.1")
	assert not upd.needs_frappe_update("16.50.0", "16.50.0")
	assert not upd.needs_frappe_update("16.0.0", "16.36.1")
	assert not upd.needs_frappe_update(None, "16.36.1")
