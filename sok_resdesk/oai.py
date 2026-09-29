"""OAI-PMH endpoint: /api/method/sok_resdesk.oai.endpoint

Point Koha (or any harvester) at that URL. Sets are the source collections
(e.g. ServantsOfKnowledge, JaiGyan).
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone
from werkzeug.wrappers import Response

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


def _record(name: str) -> dict:
	record = item_to_record(frappe.get_doc("RD Item", name))
	record["modified"] = to_utc(record["modified"])
	return record


class FrappeStore:
	def earliest(self) -> datetime | None:
		rows = frappe.db.sql("select min(modified) from `tabRD Item` where published = 1")
		return to_utc(rows[0][0]) if rows else None

	def sets(self) -> list[tuple[str, str]]:
		values = frappe.db.sql_list("select collections from `tabRD Item` where published=1 and ifnull(collections,'')!=''")
		seen: dict[str, int] = {}
		for block in values:
			for c in block.splitlines():
				c = c.strip()
				if c:
					seen[c] = seen.get(c, 0) + 1
		return [(c, c) for c, n in sorted(seen.items(), key=lambda x: -x[1]) if n > 0][:500]

	def get(self, item_id: str) -> dict | None:
		if not frappe.db.exists("RD Item", {"name": item_id, "published": 1}):
			return None
		return _record(item_id)

	def list(self, start, limit, from_, until, set_spec):
		conditions, values = ["published = 1"], {}
		if from_:
			conditions.append("modified >= %(from)s")
			values["from"] = to_system(from_)
		if until:
			conditions.append("modified <= %(until)s")
			values["until"] = to_system(until)
		if set_spec:
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
	repo = Repository(
		FrappeStore(),
		repo_id=s.repository_id or frappe.local.site,
		name=portal_title(),
		base_url=base_url(),
		admin_email=s.admin_email or "",
	)
	args = {k: v for k, v in frappe.form_dict.items() if k != "cmd"}
	return Response(repo.handle(args), content_type="text/xml; charset=utf-8")
