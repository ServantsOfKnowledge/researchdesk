import shutil
from pathlib import Path

import pytest

from sok_resdesk.core.legacy_kannada import FONTS, OFF, OPTIONS, code_for, looks_legacy

UNICODE = "ಕನ್ನಡ ಸಾಹಿತ್ಯ ಪರಿಷತ್ತು ಕರ್ನಾಟಕ ಸರ್ಕಾರದ ಗ್ರಂಥಾಲಯ ಇಲಾಖೆಯ ಹಳೆಯ ಪುಸ್ತಕಗಳು"
NUDI = "PÀ£ï£ÀqÀ ¸Á»vïAiÀÄ ¥ÀjµÀvïvÀÄ PÀgï£ÁlPÀ ¸ÀgïPÁgÀzÀ UïgÀAxÁ®AiÀÄ E¯ÁSÉAiÀÄ ºÀ¼ÉAiÀÄ ¥ÀÅ¸ïvÀPÀUÀ¼ÀÄ"
FRENCH = "Le château de la forêt était très éloigné, mais l'été dernier nous avons déjà visité l'église."
ENGLISH = "The district library keeps its records of the department for twenty years before review."


def test_text_in_an_old_font_is_recognised():
	assert looks_legacy(NUDI)


def test_unicode_kannada_english_and_french_are_left_alone():
	assert not looks_legacy(UNICODE)
	assert not looks_legacy(ENGLISH)
	assert not looks_legacy(FRENCH)


def test_a_short_scrap_is_not_judged():
	assert not looks_legacy("PÀ£ï£ÀqÀ")


def test_the_setting_has_an_off_choice_and_a_code_for_each_font():
	assert OPTIONS.splitlines()[0] == OFF
	assert code_for(OFF) is None and code_for("nonsense") is None
	assert code_for("Nudi / Baraha") == "nudi" and len(FONTS) == 15


def test_the_vendored_engine_keeps_its_licence_and_notice():
	d = Path(__file__).resolve().parents[1] / "vendor" / "kannada_font_converter"
	assert "GPL-3.0-or-later" in (d / "app.js").read_text(encoding="utf-8")[:600]
	assert "GNU GENERAL PUBLIC LICENSE" in (d / "LICENSE").read_text(encoding="utf-8")[:200]


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is not installed")
def test_the_engine_converts_both_ways():
	from sok_resdesk.core.legacy_kannada import convert

	assert convert([NUDI], "nudi", "a2u") == [UNICODE]
	assert convert([UNICODE], "nudi", "u2a") == [NUDI]
	assert convert(["", "plain English"], "nudi") == ["", "plain English"]
