"""Versions, releases and release notes (no Frappe needed, so it is unit-tested)."""

from __future__ import annotations

import re

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str | None) -> tuple[int, int, int] | None:
	"""'v0.10.1' or '0.10.1' → (0, 10, 1); anything else (a branch, a pre-release) → None."""
	m = _VERSION.match((value or "").strip())
	return tuple(int(x) for x in m.groups()) if m else None


def is_newer(candidate: str | None, current: str | None) -> bool:
	a, b = parse_version(candidate), parse_version(current)
	return bool(a and b and a > b)


def latest_release(tags, major: int | None = None) -> str | None:
	"""The highest plain release tag (vX.Y.Z), optionally within one major version."""
	best = None
	for tag in tags or []:
		v = parse_version(tag)
		if not v or (major is not None and v[0] != major):
			continue
		if best is None or v > best[0]:
			best = (v, tag if tag.startswith("v") else f"v{tag}")
	return best[1] if best else None


def releases_between(tags, current: str | None, target: str | None = None) -> list[str]:
	"""Release tags newer than current, up to target (all newer ones without a target), newest first."""
	cur, top = parse_version(current), parse_version(target) if target else None
	out = []
	for tag in tags or []:
		v = parse_version(tag)
		if v and (cur is None or v > cur) and (top is None or v <= top):
			out.append((v, tag if tag.startswith("v") else f"v{tag}"))
	return [t for _, t in sorted(set(out), reverse=True)]


def changelog_sections(text: str, current: str | None, target: str | None = None) -> list[dict]:
	"""The CHANGELOG.md entries newer than current (up to target): what an upgrade brings.

	Entries look like '## 0.10.1 (2026-09-30): title' followed by lines until the next '## '."""
	cur, top = parse_version(current), parse_version(target) if target else None
	sections, head, body = [], None, []

	def close():
		if head is None:
			return
		m = re.match(r"^##\s+v?(\d+\.\d+\.\d+)\s*(?:\(([^)]*)\))?\s*:?\s*(.*)$", head)
		if not m:
			return
		v = parse_version(m.group(1))
		if v and (cur is None or v > cur) and (top is None or v <= top):
			sections.append(
				{
					"version": m.group(1),
					"date": m.group(2) or "",
					"title": m.group(3).strip(),
					"notes": "\n".join(body).strip(),
				}
			)

	for line in (text or "").splitlines():
		if line.startswith("## "):
			close()
			head, body = line, []
		elif head is not None:
			body.append(line)
	close()
	return sections


def needs_reindex(sections: list[dict]) -> bool:
	"""A release whose notes ask for a search re-index (they say NEEDS-REINDEX or 're-index')."""
	return any("NEEDS-REINDEX" in s.get("notes", "") for s in sections)


def safe_release_ref(value: str | None) -> str:
	"""What an upgrade may be asked to install: 'latest', 'main' or a release tag vX.Y.Z."""
	value = (value or "latest").strip()
	if value in ("latest", "main") or parse_version(value):
		return value if not parse_version(value) or value.startswith("v") else f"v{value}"
	raise ValueError(f"not a release: {value!r}")
