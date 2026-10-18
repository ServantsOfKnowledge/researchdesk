"""The audit log (Settings → Governance Mode): who viewed, downloaded, searched or changed what.

Lines are only ever added, each hashed together with the one before (core/audit.py), so changing
or removing one shows when the log is checked. Nothing is recorded while Governance Mode is off.
Recording never stops a reader: if the log cannot be written, that is logged as an error (at most
once a minute) and the request carries on.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.password import get_encryption_key

from sok_resdesk import access
from sok_resdesk.core import audit as chain

EVENT = "RD Audit Event"
LOCK = "rd_audit"
SAME_VIEW_SECONDS = 300  # one person looking at one book again within this is one view


def on() -> bool:
	try:
		return bool(cint(frappe.db.get_single_value("RD Settings", "governance", cache=True)))
	except Exception:
		return False


def _key() -> bytes:
	return get_encryption_key().encode()


def _who() -> str:
	return frappe.session.user if frappe.session.user != "Guest" else f"Guest {_ip()}"


def _ip() -> str:
	return (getattr(frappe.local, "request_ip", "") or "")[:140]


def record(event: str, item: str = "", detail: str = "") -> None:
	if not on():
		return
	if event == "view":
		seen = f"rd-audit-view:{_who()}:{item}"
		if frappe.cache.get_value(seen):
			return
		frappe.cache.set_value(seen, 1, expires_in_sec=SAME_VIEW_SECONDS)
	locked = False
	try:
		# a named lock, not a row lock: it also serialises the very first line, and it is held only
		# for the few statements below
		locked = bool(frappe.db.sql("select get_lock(%s, 3)", (LOCK,))[0][0])
		if not locked:
			raise RuntimeError("the audit log is busy")
		frappe.db.savepoint("rd_audit")
		last = frappe.db.sql(
			f"select seq, row_hash from `tab{EVENT}` order by seq desc limit 1", as_dict=True
		)
		prev = last[0].row_hash if last else chain.FIRST
		row = {
			"seq": (last[0].seq if last else 0) + 1,
			"event_time": now_datetime(),
			"user": frappe.session.user,
			"event": event[:140],
			"item": (item or "")[:140],
			"detail": (detail or "")[:500],
			"ip_address": _ip(),
			"prev_hash": prev,
		}
		row["row_hash"] = chain.row_hash(prev, row, _key())
		frappe.get_doc({"doctype": EVENT, **row}).insert(ignore_permissions=True)
		frappe.db.commit()  # a reader's GET does not commit by itself
	except Exception:
		try:
			frappe.db.rollback(save_point="rd_audit")  # only the log line, never the caller's earlier work
		except Exception:
			pass
		if not frappe.cache.get_value("rd-audit-error"):
			frappe.cache.set_value("rd-audit-error", 1, expires_in_sec=60)
			frappe.log_error("Research Desk: could not write the audit log")
	finally:
		if locked:
			frappe.db.sql("select release_lock(%s)", (LOCK,))


def sink(event: str, item: str = "", detail: str = "") -> None:
	"""Hook resdesk_event_sinks: what core reports (seams.emit), shaped as the log keeps it."""
	if event == "download":
		# a viewer asking for the rest of a file it began is not a new download
		rng = frappe.local.request.headers.get("Range") if frappe.local.request else None
		if rng and not rng.replace(" ", "").startswith("bytes=0-"):
			return
	elif event == "search":
		from sok_resdesk import classified

		if classified.on():  # the words only when this is not a classified installation
			detail = detail.split(":", 1)[0]
	record(event, item, detail)


def on_login(login_manager=None) -> None:
	record("login")


def on_logout(*args, **kwargs) -> None:
	record("logout")


def _rows(step: int = 5000):
	"""The whole log in order of its number, a slice at a time."""
	after = 0
	while True:
		part = frappe.get_all(
			EVENT,
			filters={"seq": (">", after)},
			fields=["*"],
			order_by="seq asc",
			limit_page_length=step,
		)
		if not part:
			return
		yield from part
		after = part[-1]["seq"]


@frappe.whitelist()
def verify() -> dict:
	"""Check the whole log: it is intact, or the first line where it is not. The last line's number
	and hash come back too: write them down somewhere else, and a log cut short at its end shows."""
	frappe.only_for(access.MANAGER_ROLES + (access.SUPER_ROLE,))
	result = chain.verify(_rows(), _key())
	result["message"] = (
		_("The audit log is intact ({0} lines checked). Last line {1}, hash {2}.").format(
			result["checked"], result.get("last") or 0, (result.get("head") or "")[:16]
		)
		if result["ok"]
		else _("The audit log was tampered with at line {0}: {1}.").format(result["at"], result["why"])
	)
	return result
