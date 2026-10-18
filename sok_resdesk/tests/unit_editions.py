"""The standard and governance editions: the second app's shape, and that it follows Research Desk's version."""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def read(*parts):
	with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
		return f.read()


def version(text):
	return re.search(r'^__version__ = "([^"]+)"', text, re.M).group(1)


def test_the_governance_app_has_the_same_version_as_research_desk():
	core = version(read("sok_resdesk", "__init__.py"))
	assert version(read("governance", "sok_resdesk_governance", "__init__.py")) == core


def test_the_governance_app_is_a_frappe_app_that_needs_research_desk():
	base = os.path.join(ROOT, "governance", "sok_resdesk_governance")
	hooks = read("governance", "sok_resdesk_governance", "hooks.py")
	assert 'app_name = "sok_resdesk_governance"' in hooks
	assert 'required_apps = ["sok_resdesk"]' in hooks
	assert read("governance", "sok_resdesk_governance", "modules.txt").strip() == "ResDesk Governance"
	assert os.path.exists(os.path.join(base, "resdesk_governance", "__init__.py"))  # the module folder
	assert os.path.exists(os.path.join(base, "patches.txt"))


def test_research_desk_never_requires_the_governance_app():
	assert "sok_resdesk_governance" not in read("sok_resdesk", "hooks.py")
	assert "sok_resdesk_governance" not in read("pyproject.toml")


def test_every_install_path_knows_the_edition():
	for path in (
		("install.sh",),
		("upgrade.sh",),
		("scripts", "install-native.sh"),
		("docker", "create-site.sh"),
		("docker", "Dockerfile"),
		("compose.yaml",),
	):
		assert "RESDESK_EDITION" in read(*path) or "--edition" in read(*path), path


def test_an_unknown_edition_is_refused_by_the_installer():
	assert "standard|governance" in read("install.sh")
