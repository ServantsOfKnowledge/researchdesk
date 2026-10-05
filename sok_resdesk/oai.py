"""OAI-PMH endpoint: /api/method/sok_resdesk.oai.endpoint

Point Koha (or any harvester) at that URL. Sets are the source collections
(e.g. ServantsOfKnowledge, JaiGyan).

Which records it offers is set in RD Settings → OAI-PMH shares: what guests can find
(default), every published record (for a library system on an internal network), or off.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone
from werkzeug.wrappers import Response

from sok_resdesk import features
from sok_resdesk.catalogue import base_url, item_to_record, portal_title, settings
from sok_resdesk.core.oai import Repository


def _tz() -> ZoneInfo:
	return ZoneInfo(get_system_timezone() or "UTC")


def to_utc(value: datetime | None) -> datetime | None:
	"""Frappe stores naive datetimes in the system time zone; OAI wants UTC."""
	if not value:
		return None
	return value.replace(tzinfo=_tz()).astimezone(UTC)


def to_system(value: datetime | None) -> datetime | None:
	"""A harvester's UTC from/until -> naive system-time for SQL."""
	if not value:
		return None
	return value.replace(tzinfo=UTC).astimezone(_tz()).replace(tzinfo=None)


OAI_GUEST = "Records guests can find"
OAI_ALL = "All published records"
OAI_OFF = "Off"


def _where() -> str:
	"""SQL condition for the records this repository exposes (harvesters never log in)."""
	from sok_resdesk.core.access import sql_condition

	scope = settings().oai_scope or OAI_GUEST
	if scope == OAI_OFF:
		return "1=0"
	if scope == OAI_ALL:
		return "published = 1"
	return f"published = 1 and {sql_condition(settings().guest_access, member=False)}"


def _record(name: str) -> dict:
	record = item_to_record(frappe.get_doc("RD Item", name))
	record["modified"] = to_utc(record["modified"])
	return record


class FrappeStore:
	def earliest(self) -> datetime | None:
		rows = frappe.db.sql(f"select min(modified) from `tabRD Item` where {_where()}")
		return to_utc(rows[0][0]) if rows else None

	def sets(self) -> list[tuple[str, str]]:
		values = frappe.db.sql_list(
			f"select collections from `tabRD Item` where {_where()} and ifnull(collections,'')!=''"
		)
		seen: dict[str, int] = {}
		for block in values:
			for c in block.splitlines():
				c = c.strip()
				if c:
					seen[c] = seen.get(c, 0) + 1
		sets = [(c, c) for c, n in sorted(seen.items(), key=lambda x: -x[1]) if n > 0][:500]
		curated = frappe.get_all(
			"RD Collection", filters={"published": 1}, fields=["name", "title"], order_by="sort_order, title"
		)
		if curated:
			sets.append(("rd", f"{portal_title()} collections"))
			sets += [(f"rd:{c.name}", c.title) for c in curated]
		return sets

	def get(self, item_id: str) -> dict | None:
		if not frappe.db.sql(f"select 1 from `tabRD Item` where name=%s and {_where()}", item_id):
			return None
		return _record(item_id)

	def list(self, start, limit, from_, until, set_spec):
		conditions, values = [_where()], {}
		if from_:
			conditions.append("modified >= %(from)s")
			values["from"] = to_system(from_)
		if until:
			conditions.append("modified <= %(until)s")
			values["until"] = to_system(until)
		if set_spec == "rd":
			conditions.append(
				"exists (select 1 from `tabRD Item Collection` c where c.parent=`tabRD Item`.name)"
			)
		elif set_spec and set_spec.startswith("rd:"):
			conditions.append(
				"exists (select 1 from `tabRD Item Collection` c where c.parent=`tabRD Item`.name "
				"and c.collection=%(curated)s)"
			)
			values["curated"] = set_spec[3:]
		elif set_spec:
			conditions.append("concat('\n', collections, '\n') like %(set)s")
			values["set"] = f"%\n{set_spec}\n%"
		where = " and ".join(conditions)
		total = frappe.db.sql(f"select count(*) from `tabRD Item` where {where}", values)[0][0]
		names = frappe.db.sql_list(
			f"select name from `tabRD Item` where {where} order by modified asc, name asc limit %(limit)s offset %(start)s",
			{**values, "limit": int(limit), "start": int(start)},
		)
		return [_record(n) for n in names], total


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def endpoint(**kwargs):
	s = settings()
	if (s.oai_scope or OAI_GUEST) == OAI_OFF or not features.on("sharing"):
		raise frappe.PageDoesNotExistError
	repo = Repository(
		FrappeStore(),
		repo_id=s.repository_id or frappe.local.site,
		name=portal_title(),
		base_url=base_url(),
		admin_email=s.admin_email or "",
	)
	args = {k: v for k, v in frappe.form_dict.items() if k != "cmd"}
	return Response(repo.handle(args), content_type="text/xml; charset=utf-8")
