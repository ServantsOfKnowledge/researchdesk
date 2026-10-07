"""Typing in your own language: the vendored jquery.ime lists point at real files, and the
language box (ime.js) finds a language from a code or a bit of its name."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PUBLIC = Path(__file__).resolve().parents[1] / "public"
VENDOR = PUBLIC / "vendor" / "jquery.ime"
IME_JS = PUBLIC / "js" / "ime.js"


def _sources():
	text = (VENDOR / "ime-sources.js").read_text(encoding="utf-8")
	langs = json.loads(re.search(r"\$\.ime\.languages = (\{.*?\n\});\n", text, re.S).group(1))
	srcs = json.loads(re.search(r"\$\.ime\.sources = (\{.*?\n\});\n", text, re.S).group(1))
	return langs, srcs


def test_every_input_method_has_its_rules_file():
	langs, srcs = _sources()
	assert {"kn", "hi", "ta", "te", "ml"} <= set(langs)
	for lang, info in langs.items():
		assert info["autonym"] and info["inputmethods"], lang
		for method in info["inputmethods"]:
			assert (VENDOR / srcs[method]["source"]).is_file(), method
			assert srcs[method]["source"].startswith(f"rules/{lang}/")
	assert (VENDOR / "MIT-LICENSE").is_file() and (VENDOR / "jquery.ime.min.js").is_file()


def test_kannada_can_be_typed_in_latin_letters():
	langs, _ = _sources()
	assert "kn-transliteration" in langs["kn"]["inputmethods"]  # ime.js starts people on it


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_language_box_finds_a_language_from_a_code_or_a_name():
	script = (
		"global.window = {};"
		f"const L = require({json.dumps(str(IME_JS))});"
		"const o = {kan: 'Kannada', kas: 'Kashmiri', hin: 'Hindi', eng: 'English'};"
		"const t = ['kan', 'Kannada', 'kan — Kannada', 'HIN', 'h', 'ka', 'xx', ''];"
		"console.log(JSON.stringify(t.map((x) => L.resolve(x, o).code)));"
	)
	out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
	assert json.loads(out) == ["kan", "kan", "kan", "hin", "hin", None, None, ""]
