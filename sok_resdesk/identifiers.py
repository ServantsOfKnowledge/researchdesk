"""Persistent identifiers: every book gets an ARK when it is first catalogued, the portal resolves
ARKs itself (`<portal>/ark:/<naan>/<name>`), and a book that is deleted leaves a tombstone, so a
permanent link never ends in "page not found".

The ARK rules themselves (minting, check characters, parsing) are in core/ark.py.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from sok_resdesk.core import ark as core

MANAGERS = ("System Manager", "ResDesk Manager")
SHOULDER = re.compile(r"^[bcdfghjkmnpqrstvwxz]+[0-9]")


def naan_and_shoulder() -> tuple[str, str]:
	s = frappe.db.get_singles_dict("RD Settings")
	naan = (s.get("ark_naan") or core.TEST_NAAN).strip()
	shoulder = (s.get("ark_shoulder") or core.DEFAULT_SHOULDER).strip()
	return core.validate_naan(naan), core.validate_shoulder(shoulder)


def _series(shoulder: str) -> str:
	return f"rd-ark-{shoulder}"


def _reserve(shoulder: str, count: int) -> int:
	"""Take `count` counters for a shoulder at once; returns the first. The Series row is locked
	until the transaction ends, so two workers never get the same counter."""
	key = _series(shoulder)
	row = frappe.db.sql("select `current` from `tabSeries` where name=%s for update", key)
	if not row:
		frappe.db.sql("insert into `tabSeries` (name, `current`) values (%s, 0)", key)
		current = 0
	else:
		current = cint(row[0][0])
	frappe.db.sql("update `tabSeries` set `current`=%s where name=%s", (current + count, key))
	return current


def mint_next() -> str:
	naan, shoulder = naan_and_shoulder()
	return core.mint(naan, shoulder, _reserve(shoulder, 1))


def url_of(ark: str) -> str:
	from sok_resdesk.catalogue import base_url

	return f"{base_url()}/{ark}"


def assign_missing(batch: int = 2000) -> int:
	"""Give every book without an ARK one, oldest first (the patch for existing catalogues).
	Returns how many were given."""
	naan, shoulder = naan_and_shoulder()
	done = 0
	while True:
		names = frappe.db.sql_list(
			"""select name from `tabRD Item` where ifnull(persistent_id, '') = ''
			order by creation asc limit %s""",
			batch,
		)
		if not names:
			return done
		first = _reserve(shoulder, len(names))
		rows = [(core.mint(naan, shoulder, first + i), name) for i, name in enumerate(names)]
		for ark, name in rows:
			frappe.db.sql("update `tabRD Item` set persistent_id=%s where name=%s", (ark, name))
		frappe.db.commit()
		done += len(rows)


def remint(old_naan: str, new_naan: str) -> int:
	"""Make every ARK minted under the test NAAN again under the library's own, keeping its name
	(only the NAAN and the check character change). Books and tombstones."""
	core.validate_naan(new_naan)
	changed = 0
	for doctype in ("RD Item", "RD Tombstone"):
		field = "persistent_id" if doctype == "RD Item" else "ark"
		rows = frappe.db.sql(
			f"select name, `{field}` from `tab{doctype}` where `{field}` like %s",
			(f"ark:/{old_naan}/%",),
		)
		for name, old in rows:
			m = SHOULDER.match(core.parse(old)["name"])
			if not m:
				continue
			new = core.mint(new_naan, m[0], core.counter_of(old, m[0]))
			frappe.db.sql(f"update `tab{doctype}` set `{field}`=%s where name=%s", (new, name))
			changed += 1
	frappe.db.commit()
	return changed


def on_settings_change(doc, method=None) -> None:
	"""RD Settings: a NAAN entered in place of the test one re-mints every ARK under it."""
	before = doc.get_doc_before_save()
	old = (before.get("ark_naan") if before else None) or core.TEST_NAAN
	new = (doc.get("ark_naan") or core.TEST_NAAN).strip()
	if old != new and old == core.TEST_NAAN:
		frappe.enqueue(
			"sok_resdesk.identifiers.remint",
			queue="long",
			old_naan=old,
			new_naan=new,
			enqueue_after_commit=True,
			job_id="resdesk-ark-remint",
		)


def validate_settings(doc) -> None:
	"""Called from RD Settings.validate: a NAAN and shoulder ARKs can be minted with, and a real
	NAAN stays (ARKs under it are promises to the world)."""
	naan = (doc.get("ark_naan") or core.TEST_NAAN).strip()
	shoulder = (doc.get("ark_shoulder") or core.DEFAULT_SHOULDER).strip()
	try:
		doc.ark_naan, doc.ark_shoulder = core.validate_naan(naan), core.validate_shoulder(shoulder)
	except core.ArkError as e:
		frappe.throw(str(e), title=_("Persistent Identifiers"))
	before = doc.get_doc_before_save()
	old = (before.get("ark_naan") if before else None) or core.TEST_NAAN
	if old != core.TEST_NAAN and doc.ark_naan != old:
		frappe.throw(
			_(
				"The ARK NAAN is {0}, and books have ARKs under it that people may have cited. It can't be changed here; ask the ARK Alliance about moving it."
			).format(old),
			title=_("Persistent Identifiers"),
		)


# -- tombstones ------------------------------------------------------------------------------------


def leave_tombstone(item, reason: str = "Deleted", replaced_by: str = "") -> None:
	"""A deleted book keeps its ARK alive: the ARK then explains what happened."""
	if not item.get("persistent_id") or frappe.db.exists("RD Tombstone", {"ark": item.persistent_id}):
		return
	frappe.get_doc(
		{
			"doctype": "RD Tombstone",
			"ark": item.persistent_id,
			"item_id": item.name,
			"title": (item.get("title") or "")[:140],
			"creators": (item.get("creator_display") or "")[:140],
			"year": item.get("year") or None,
			"reason": reason,
			"replaced_by": replaced_by,
			"withdrawn_on": now_datetime(),
		}
	).insert(ignore_permissions=True)


def on_item_trash(doc, method=None) -> None:
	leave_tombstone(doc)


# -- the resolver ----------------------------------------------------------------------------------

try:
	from frappe.website.page_renderers.base_renderer import BaseRenderer
except ImportError:  # outside a bench (plain pytest): the resolver isn't used there
	BaseRenderer = object


def _wants_info() -> bool:
	"""ARK inflections: `?info` (or a bare `?`) asks for metadata about the object, not the object."""
	request = getattr(frappe.local, "request", None)
	if not request:
		return False
	if "info" in (request.args or {}):
		return True
	raw = request.environ.get("RAW_URI") or request.environ.get("REQUEST_URI") or ""
	return raw.endswith("?") or raw.endswith("??")


def resolve(text: str) -> dict:
	"""Where an ARK leads: {kind: book | tombstone | unknown, …}."""
	try:
		parsed = core.parse(text)
	except core.ArkError:
		return {"kind": "unknown"}
	if not parsed["valid"]:
		return {"kind": "unknown", "ark": parsed["ark"]}
	leaf = core.leaf_of(parsed["qualifier"])
	item = frappe.db.get_value(
		"RD Item",
		{"persistent_id": parsed["ark"]},
		["name", "published", "title", "creator_display", "year", "visibility"],
		as_dict=True,
	)
	if item and cint(item.published):
		return {"kind": "book", "ark": parsed["ark"], "item": item, "leaf": leaf}
	stone = frappe.db.get_value(
		"RD Tombstone", {"ark": parsed["ark"]}, ["name", "item_id", "title"], as_dict=True
	)
	if item or stone:
		return {"kind": "tombstone", "ark": parsed["ark"], "item": item, "tombstone": stone}
	return {"kind": "unknown", "ark": parsed["ark"]}


class ArkPage(BaseRenderer):
	"""`/ark:/<naan>/<name>[/n<leaf>]`: the book's page (at that leaf), its metadata with `?info`,
	or a tombstone for a book that is gone (hooks.py page_renderer)."""

	def can_render(self):
		return self.path.lower().startswith("ark:")

	def render(self):
		from werkzeug.utils import redirect
		from werkzeug.wrappers import Response

		from sok_resdesk.access import can_find

		where = resolve(self.path)
		if where["kind"] == "book":
			item = where["item"]
			url = f"/library/item/{item.name}" + (
				f"?page={where['leaf']}" if where["leaf"] is not None else ""
			)
			if _wants_info():
				if not can_find(item.visibility):
					return Response(core.erc("", "", "", url_of(where["ark"])), mimetype="text/plain")
				from sok_resdesk.catalogue import base_url

				text = core.erc(item.creator_display, item.title, item.year, base_url() + url)
				return Response(text, mimetype="text/plain")
			return redirect(url, 302)
		if where["kind"] == "tombstone":
			return redirect(f"/library/withdrawn?ark={where['ark']}", 302)
		from frappe.website.page_renderers.not_found_page import NotFoundPage

		return NotFoundPage(self.path).render()
