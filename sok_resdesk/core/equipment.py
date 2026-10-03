"""What the server has: programs, Python packages and versions (for requirements.py).

Pure Python, standard library only, so it is tested without a site.
"""

from __future__ import annotations

import importlib.metadata
import re
import shutil
import subprocess

VERSION = re.compile(r"(\d+(?:\.\d+){1,3})")


def version_tuple(text: str | None) -> tuple[int, ...]:
	"""'10.11.6-MariaDB' → (10, 11, 6); '' → ()."""
	m = VERSION.search(text or "")
	return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def at_least(found: str | None, need: str) -> bool:
	have, want = version_tuple(found), version_tuple(need)
	if not have:
		return False
	n = max(len(have), len(want))
	return have + (0,) * (n - len(have)) >= want + (0,) * (n - len(want))


def program(name: str, args: tuple[str, ...] = ("--version",), timeout: int = 15) -> dict:
	"""{path, version, line}: where the program is and the version it reports ({} when absent)."""
	path = shutil.which(name)
	if not path:
		return {}
	try:
		out = subprocess.run([path, *args], capture_output=True, text=True, timeout=timeout)
		line = ((out.stdout or "") + (out.stderr or "")).strip().splitlines()
	except (OSError, subprocess.TimeoutExpired):
		line = []
	first = line[0] if line else ""
	m = VERSION.search(first)
	return {"path": path, "version": m.group(1) if m else "", "line": first}


def package(dist: str) -> str | None:
	"""The installed version of a Python distribution, or None."""
	try:
		return importlib.metadata.version(dist)
	except importlib.metadata.PackageNotFoundError:
		return None


def item(
	key: str,
	group: str,
	label: str,
	purpose: str,
	state: str,
	found: str = "",
	need: str = "",
	fix: str = "",
	install: str = "",
) -> dict:
	"""One line of the requirements list. state: ok, missing, old, warn, off (not needed now)."""
	return {
		"key": key,
		"group": group,
		"label": label,
		"purpose": purpose,
		"state": state,
		"found": found,
		"need": need,
		"fix": fix,
		"install": install,
	}


def summary(items: list[dict]) -> dict:
	"""{ok, missing, warn}: counts, with 'missing' covering missing and too old."""
	out = {"ok": 0, "missing": 0, "warn": 0}
	for i in items:
		if i["state"] == "ok":
			out["ok"] += 1
		elif i["state"] in ("missing", "old"):
			out["missing"] += 1
		elif i["state"] == "warn":
			out["warn"] += 1
	return out
