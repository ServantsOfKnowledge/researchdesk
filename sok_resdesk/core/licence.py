"""Creative Commons licences for display: the badge to show and what it means, from a licence URL.

A book carries a licence as a URL (https://creativecommons.org/licenses/by-sa/4.0/). The portal shows
the licence's badge, linked to that URL, instead of the address. The badges are small SVG files
served by the portal itself (public/images/licences/), so showing them asks nothing of another
server. Pure Python (no Frappe), unit-tested directly; scripts/make_licence_badges.py draws them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BADGE_DIR = "/assets/sok_resdesk/images/licences"
# the licence elements, in the order CC writes them
PARTS = {
	"by": "Attribution",
	"nc": "NonCommercial",
	"nd": "NoDerivatives",
	"sa": "ShareAlike",
}
_LICENCE = re.compile(r"creativecommons\.org/licenses/(by(?:-nc)?(?:-nd|-sa)?)/(\d\.\d)(?:/(\w+))?", re.I)
_ZERO = re.compile(r"creativecommons\.org/publicdomain/zero/(\d\.\d)", re.I)
_MARK = re.compile(r"creativecommons\.org/publicdomain/mark/(\d\.\d)", re.I)


@dataclass(frozen=True)
class Licence:
	code: str  # by-sa-4.0, zero-1.0, mark-1.0
	label: str  # CC BY-SA 4.0
	name: str  # Attribution-ShareAlike 4.0 International
	url: str
	badge: str  # the badge's address on the portal


def _version(v: str, jurisdiction: str = "") -> str:
	return (
		f"{v} International" if not jurisdiction or jurisdiction == "deed" else f"{v} {jurisdiction.upper()}"
	)


def parse(url: str) -> Licence | None:
	"""The Creative Commons licence a URL names, else None (any other licence stays a plain link)."""
	u = (url or "").strip()
	if not u:
		return None
	m = _LICENCE.search(u)
	if m:
		kind, version = m.group(1).lower(), m.group(2)
		elements = kind.split("-")
		name = "-".join(PARTS[e] for e in elements)
		return Licence(
			f"{kind}-{version}",
			f"CC {kind.upper()} {version}",
			f"{name} {_version(version)}",
			u,
			f"{BADGE_DIR}/{kind}-{version}.svg",
		)
	m = _ZERO.search(u)
	if m:
		v = m.group(1)
		return Licence(
			f"zero-{v}",
			f"CC0 {v}",
			f"CC0 {v} Universal (public domain dedication)",
			u,
			f"{BADGE_DIR}/zero-{v}.svg",
		)
	m = _MARK.search(u)
	if m:
		v = m.group(1)
		return Licence(
			f"mark-{v}", "Public Domain Mark", f"Public Domain Mark {v}", u, f"{BADGE_DIR}/mark-{v}.svg"
		)
	return None


def all_codes() -> list[str]:
	"""The badges that exist: every licence kind in 3.0 and 4.0, CC0 and the Public Domain Mark."""
	kinds = ["by", "by-sa", "by-nd", "by-nc", "by-nc-sa", "by-nc-nd"]
	return [f"{k}-{v}" for v in ("4.0", "3.0") for k in kinds] + ["zero-1.0", "mark-1.0"]
