"""The vendored copy's version can be read (scripts/check_vendored.py)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_vendored.py"


def test_each_vendored_library_reports_its_version():
	spec = importlib.util.spec_from_file_location("check_vendored", SCRIPT)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	for name, (path, pattern) in module.VENDORED.items():
		assert module.vendored_version(path, pattern), name
	assert module.vendored_version(*module.VENDORED["jquery.ime"]) == "0.2.0-2"
