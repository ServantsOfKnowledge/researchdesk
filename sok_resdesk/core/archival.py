"""Archival description: the hierarchy of an archive's papers (fonds, series, file, item) in the
shape of ISAD(G), and its exchange form, EAD3. Pure Python (no Frappe), so it is unit-tested directly.

Each unit has a reference code, a title, a level, dates, an extent and a creator (the ISAD(G)
essentials) and, as far as the archive has them, the rest: history, scope and content, access and
reproduction conditions, language, finding aids and notes. Units nest by their parent.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape, quoteattr

LEVELS = ["Fonds", "Sub-fonds", "Collection", "Series", "Sub-series", "File", "Item"]
EAD_LEVEL = {
	"Fonds": "fonds",
	"Sub-fonds": "subfonds",
	"Collection": "collection",
	"Series": "series",
	"Sub-series": "subseries",
	"File": "file",
	"Item": "item",
}
# a unit's children may be of these levels: nothing is nested under an Item, a Fonds holds
# anything below it, and so on down; anything may sit directly under a Collection
RANK = {lvl: n for n, lvl in enumerate(LEVELS)}
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
NS = "http://ead3.archivists.org/schema/"


def valid_code(code: str) -> bool:
	"""A reference code that is safe in a web address and a file name: letters, digits, . _ -"""
	return bool(CODE.match(code or ""))


def child_allowed(parent_level: str, level: str) -> str:
	"""'' when a unit of `level` may sit under one of `parent_level` ('' for none: a top unit),
	else why not."""
	if not parent_level:
		return (
			""
			if level in ("Fonds", "Collection")
			else f"A {level.lower()} sits inside a fonds or collection."
		)
	if parent_level == "Item":
		return "Nothing is described under an item."
	if level in ("Fonds", "Collection"):
		return f"A {level.lower()} is the top of its own hierarchy: it has no parent."
	if level == "Sub-fonds":
		return "" if parent_level in ("Fonds", "Sub-fonds") else "A sub-fonds sits under a fonds."
	if parent_level == "Collection":
		return ""  # a collection holds anything below it
	if RANK[level] > RANK[parent_level]:
		return ""
	return f"A {level.lower()} cannot sit under a {parent_level.lower()}."


def ancestors(units: dict[str, dict], name: str) -> list[dict]:
	"""The unit's parents from the top down (not the unit itself)."""
	out, seen = [], {name}
	cur = units.get(name, {}).get("parent")
	while cur and cur in units and cur not in seen:
		seen.add(cur)
		out.append(units[cur])
		cur = units[cur].get("parent")
	return list(reversed(out))


def children_of(units: list[dict]) -> dict[str, list[dict]]:
	out: dict[str, list[dict]] = {}
	for u in units:
		out.setdefault(u.get("parent") or "", []).append(u)
	for kids in out.values():
		kids.sort(key=lambda u: (u.get("sort") or 0, natural(u.get("ref") or "")))
	return out


def natural(text: str) -> list:
	"""A sort key that puts 'MS-2' before 'MS-10'."""
	return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def _paras(text: str) -> str:
	parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
	return "".join(f"<p>{escape(p)}</p>" for p in parts)


def _block(tag: str, text: str) -> str:
	return f"<{tag}>{_paras(text)}</{tag}>" if (text or "").strip() else ""


def _did(u: dict) -> str:
	parts = [
		f"<unitid>{escape(u.get('ref') or '')}</unitid>",
		f"<unittitle>{escape(u.get('title') or '')}</unittitle>",
	]
	if u.get("date_text") or u.get("year_from"):
		text = u.get("date_text") or f"{u.get('year_from')}–{u.get('year_to') or u.get('year_from')}"
		if u.get("year_from"):
			a, b = u["year_from"], u.get("year_to") or u["year_from"]
			parts.append(
				f'<unitdatestructured><daterange><fromdate standarddate="{a}">{a}</fromdate>'
				f'<todate standarddate="{b}">{b}</todate></daterange></unitdatestructured>'
			)
		parts.append(f"<unitdate>{escape(str(text))}</unitdate>")
	if u.get("extent"):
		parts.append(
			f'<physdescstructured physdescstructuredtype="otherphysdescstructuredtype" coverage="whole">'
			f"<quantity>1</quantity><unittype>{escape(u['extent'])}</unittype></physdescstructured>"
		)
	if u.get("physical"):
		parts.append(f"<physdesc>{escape(u['physical'])}</physdesc>")
	if u.get("creator"):
		parts.append(f"<origination><name><part>{escape(u['creator'])}</part></name></origination>")
	if u.get("language"):
		parts.append(
			f"<langmaterial><language langcode={quoteattr(u['language'][:3])}>{escape(u['language'])}</language></langmaterial>"
		)
	return "<did>" + "".join(parts) + "</did>"


def _notes(u: dict) -> str:
	return "".join(
		(
			_block("bioghist", u.get("admin_history")),
			_block("custodhist", u.get("custodial_history")),
			_block("scopecontent", u.get("scope_content")),
			_block("arrangement", u.get("arrangement")),
			_block("accessrestrict", u.get("access_conditions")),
			_block("userestrict", u.get("reproduction_conditions")),
			_block("otherfindaid", u.get("finding_aids")),
			_block("relatedmaterial", u.get("related_materials")),
			_block("odd", u.get("notes")),
		)
	)


def _component(u: dict, kids: dict[str, list[dict]], depth: int = 0) -> str:
	inner = "".join(_component(k, kids, depth + 1) for k in kids.get(u["name"], []))
	return f'<c level="{EAD_LEVEL.get(u.get("level"), "otherlevel")}">{_did(u)}{_notes(u)}{inner}</c>'


def ead3(root: str, units: list[dict], agency: str, today: str) -> str:
	"""An EAD3 finding aid of the unit `root` and everything under it. `units`: dicts with name,
	parent, ref, title, level and the optional description fields."""
	by_name = {u["name"]: u for u in units}
	if root not in by_name:
		raise KeyError(root)
	top = by_name[root]
	kids = children_of(units)
	body = "".join(_component(k, kids) for k in kids.get(root, []))
	return (
		'<?xml version="1.0" encoding="UTF-8"?>\n'
		f'<ead xmlns="{NS}">'
		f"<control><recordid>{escape(top['ref'])}</recordid>"
		f"<filedesc><titlestmt><titleproper>{escape(top['title'])}</titleproper></titlestmt></filedesc>"
		'<maintenancestatus value="derived"/><publicationstatus value="inherit"/>'
		f"<maintenanceagency><agencyname>{escape(agency)}</agencyname></maintenanceagency>"
		'<maintenancehistory><maintenanceevent><eventtype value="derived"/>'
		f"<eventdatetime standarddatetime={quoteattr(today)}>{escape(today)}</eventdatetime>"
		'<agenttype value="machine"/><agent>SOK Research Desk</agent></maintenanceevent></maintenancehistory>'
		"</control>"
		f'<archdesc level="{EAD_LEVEL.get(top.get("level"), "otherlevel")}">{_did(top)}{_notes(top)}'
		+ (f"<dsc>{body}</dsc>" if body else "")
		+ "</archdesc></ead>\n"
	)
