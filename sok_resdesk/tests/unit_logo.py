"""One default logo: the Servants of Knowledge one, named the same everywhere (and shipped)."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LOGO = "/assets/sok_resdesk/images/sok-logo.png"


def _paths(file: str, pattern: str) -> list[str]:
	return re.findall(pattern, (APP / file).read_text(encoding="utf-8"))


def test_every_default_is_the_servants_of_knowledge_logo():
	assert _paths("resdesk/doctype/rd_settings/rd_settings.py", r'DEFAULT_LOGO = "([^"]+)"') == [LOGO]
	assert _paths("help.py", r'HELP_LOGO = "([^"]+)"') == [LOGO]
	hooks = _paths("hooks.py", r'(?:app_logo_url = |"logo": )"([^"]+)"')
	assert hooks == [LOGO, LOGO]


def test_the_logo_is_shipped_with_the_app():
	assert (APP / "public" / "images" / "sok-logo.png").is_file()


def test_the_default_logo_patch_is_registered():
	assert "sok_resdesk.patches.v0_75.default_logo" in (APP / "patches.txt").read_text()
