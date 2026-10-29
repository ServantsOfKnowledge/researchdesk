"""Self-service kiosk: a member scans their card, types their PIN and borrows books at a screen by the door.

The kiosk is a device logged in as its own account with the role ResDesk Kiosk. A member proves who they are
with the card number and the PIN they chose on the portal (My library); five wrong tries lock that card at the
kiosk for fifteen minutes, and the answer is the same for a card that does not exist, a wrong PIN and a member
who cannot borrow. A session lasts five minutes from the last thing done, borrows at most ten books and cannot
return books or change anything else about the member. Loans go through the same rules as at the desk.
"""

from __future__ import annotations

import hashlib
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from sok_resdesk import access, features, lending
from sok_resdesk.core import lending as rules

ROLE = "ResDesk Kiosk"
SESSION_SECONDS = 300  # from the last thing done
SESSION_MAX_SECONDS = 1800  # however busy
MAX_TRIES = 5  # wrong PINs for one card
LOCK_SECONDS = 900
MAX_DEVICE_FAILURES = 20  # wrong tries by one kiosk account, for any cards
DEVICE_SECONDS = 600
MAX_BORROW = 10  # books in one session


def _device() -> None:
	if not features.on("lending"):
		frappe.throw(features.off_message("lending"), title=_("Switched off"))
	frappe.only_for((ROLE,) + tuple(access.MANAGER_ROLES))


def _refuse() -> None:
	frappe.throw(
		_("The card or PIN is not right, or it cannot be used here. Please ask at the desk."),
		frappe.AuthenticationError,
	)


def _count(key: str, seconds: int, by: int = 1) -> int:
	"""Add to a counter that expires, in one step (two tries at once cannot both read the old number)."""
	cache = frappe.cache()
	k = cache.make_key(key)
	n = cache.incrby(k, by)
	if n == by:
		cache.expire(k, seconds)
	return int(n)


def _check_pin(patron: str, pin: str) -> bool:
	from frappe.utils.password import check_password, passlibctx

	if not (patron and pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 6 and lending.has_pin(patron)):
		passlibctx.dummy_verify()  # no such card, or none with a PIN, takes as long as a wrong PIN
		return False
	try:
		check_password(patron, pin, doctype="RD Patron", fieldname=lending.PIN_FIELD)
		return True
	except frappe.AuthenticationError:
		return False


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def start(card: str, pin: str) -> dict:
	"""Begin a session: the member's card number and PIN. Returns a token for the session and what they have."""
	_device()
	code = (card or "").strip().upper()[:60]
	name = frappe.db.get_value("RD Patron", code, "name") if code else None
	user = frappe.session.user
	if (
		cint(frappe.cache().get(frappe.cache().make_key(f"rd_kiosk_device:{user}")) or 0)
		>= MAX_DEVICE_FAILURES
	):
		_refuse()  # this kiosk has failed too often, for any cards
	# counted before the PIN is looked at, on the member the card names (any spelling of it), so a burst of
	# parallel tries cannot all see the old count
	key = f"rd_kiosk_tries:{name or hashlib.sha256(code.encode()).hexdigest()[:20]}"
	if _count(key, LOCK_SECONDS) > MAX_TRIES:
		_refuse()
	ok = _check_pin(name, str(pin or "").strip())
	if ok:
		member = lending._patron(name)
		ok = member.status not in (rules.PENDING, rules.LISTED, rules.REJECTED)
	if not ok:
		_count(f"rd_kiosk_device:{user}", DEVICE_SECONDS)
		_refuse()
	frappe.cache().delete_value(key)
	token = frappe.generate_hash(length=32)
	frappe.cache().set_value(
		f"rd_kiosk:{token}", f"{name}|{user}|{int(time.time())}", expires_in_sec=SESSION_SECONDS
	)
	return {"token": token, "snapshot": lending.snapshot(name)}


def _member(token: str) -> str:
	"""The member of a live session: issued to this kiosk account, not older than the longest session."""
	cache = frappe.cache()
	value = cache.get_value(f"rd_kiosk:{token}") if token else None
	try:
		name, user, started = str(value).split("|")
		live = user == frappe.session.user and time.time() - int(started) < SESSION_MAX_SECONDS
	except ValueError:
		live = False
	if not live:
		frappe.throw(_("Your session has ended. Please scan your card again."), frappe.PermissionError)
	cache.set_value(f"rd_kiosk:{token}", value, expires_in_sec=SESSION_SECONDS)
	return name


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def borrow(token: str, barcode: str) -> dict:
	"""Lend the book with this barcode to the member of this session."""
	_device()
	name = _member(token)
	count_key = f"rd_kiosk_n:{token}"
	if _count(count_key, SESSION_MAX_SECONDS) > MAX_BORROW:
		_count(count_key, SESSION_MAX_SECONDS, -1)
		frappe.throw(_("That is the most books to borrow at once here. Please finish, or ask at the desk."))
	try:
		return lending.lend(name, barcode)
	except Exception:
		_count(count_key, SESSION_MAX_SECONDS, -1)  # a refused loan is not a book borrowed
		raise


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def renew(token: str, loan: str) -> dict:
	_device()
	name = _member(token)
	if frappe.db.get_value("RD Loan", loan, "patron") != name:
		frappe.throw(_("That is not your open loan."), frappe.PermissionError)
	member = lending._patron(name)
	out = lending._renew(lending._open_loan(loan), member)
	out["snapshot"] = lending.snapshot(name)
	return out


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def end(token: str) -> dict:
	_device()
	frappe.cache().delete_value(f"rd_kiosk:{token}")
	frappe.cache().delete_value(f"rd_kiosk_n:{token}")
	return {"ended": 1}
