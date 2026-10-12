#!/usr/bin/env python3
"""Is any library copied into this app behind its latest release? Run weekly by CI
(.github/workflows/vendored.yml); exits 1 and says which when one is.

Add a library by adding a row to VENDORED: its npm name, the file that carries its version and a
pattern that finds the version in that file."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORED = {
	"jquery.ime": (
		"sok_resdesk/public/vendor/jquery.ime/jquery.ime.min.js",
		r"jquery\.ime - v([\w.\-]+?)(?:\+|\s)",
	),
}


def vendored_version(path: str, pattern: str) -> str | None:
	m = re.search(pattern, (ROOT / path).read_text(encoding="utf-8", errors="replace")[:500])
	return m.group(1) if m else None


def latest_version(npm_name: str) -> str:
	with urllib.request.urlopen(f"https://registry.npmjs.org/{npm_name}/latest", timeout=20) as r:
		return json.load(r)["version"]


def main() -> int:
	behind = []
	for name, (path, pattern) in VENDORED.items():
		have, latest = vendored_version(path, pattern), latest_version(name)
		print(f"{name}: vendored {have}, latest {latest}")
		if have != latest:
			behind.append(name)
	if behind:
		print("Behind: " + ", ".join(behind) + ". Refresh with the script named in docs/technology.md.")
	return 1 if behind else 0


if __name__ == "__main__":
	sys.exit(main())
