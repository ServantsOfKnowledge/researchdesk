"""Paying fines online, through Razorpay payment links (Settings → Members and Lending → Online payments).

A member with fines due presses *Pay online* on My library. Research Desk makes a Razorpay payment link for
what they owe and sends them to it: the card or UPI details go to Razorpay, never here. When Razorpay's signed
webhook says the link was paid, the fines are marked Paid. Nothing is sent by email or SMS. It is off until the
library gives Razorpay's keys, and refused in Classified mode (no outside connection).

Set the webhook in the Razorpay dashboard to https://<your portal>/api/method/sok_resdesk.payments.webhook for
the event *payment_link.paid*, with a secret you also type into Settings.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.utils import add_days, flt, get_datetime, now_datetime, nowdate

from sok_resdesk import features, lending, seams
from sok_resdesk.core import payments as rules
from sok_resdesk.ratelimit import rate_limit

PROVIDER = "Razorpay"


def _keys() -> tuple[str, str, str]:
	s = frappe.get_single("RD Settings")
	return (
		(s.get("razorpay_key_id") or "").strip(),
		(s.get_password("razorpay_key_secret", raise_exception=False) or "").strip(),
		(s.get_password("razorpay_webhook_secret", raise_exception=False) or "").strip(),
	)


def configured() -> bool:
	"""Online payment is on: the feature, Razorpay chosen, all three keys given, and not Classified mode."""
	if not features.on("lending") or seams.classified():
		return False
	if (frappe.db.get_single_value("RD Settings", "payment_provider") or "Off") != PROVIDER:
		return False
	return all(_keys())


def _safe_link(url: str) -> bool:
	"""Razorpay's own address only: a link we send a member to must not be one a bad answer chose."""
	p = urlparse(url or "")
	host = p.hostname or ""
	return p.scheme == "https" and (
		host == "rzp.io" or host.endswith(".razorpay.com") or host == "razorpay.com"
	)


@frappe.whitelist(methods=["POST"])
def start() -> dict:
	"""A link to pay everything the signed-in member owes."""
	member = lending._me()
	frappe.db.get_value("RD Patron", member.name, "name", for_update=True)  # two clicks make one link
	if not configured():
		frappe.throw(_("Online payment is not set up. Please pay at the library desk."))
	fines = frappe.get_all(
		"RD Fine",
		filters={"patron": member.name, "status": "Due"},
		fields=["name", "amount"],
		order_by="name asc",
	)
	if not fines:
		frappe.throw(_("You have no fines to pay."))
	amount = round(sum(f.amount for f in fines), 2)
	names = "\n".join(f.name for f in fines)
	# the same fines, still unpaid, asked for again: the link made a moment ago is still good
	same = frappe.get_all(
		"RD Fine Payment",
		filters={
			"patron": member.name,
			"status": "Created",
			"fine_names": names,
			"creation": (">", add_days(now_datetime(), -1)),
		},
		fields=["name", "link_url", "amount"],
		limit=1,
	)
	if same and flt(same[0].amount) == amount and _safe_link(same[0].link_url):
		return {"url": same[0].link_url}
	pay = frappe.get_doc(
		{
			"doctype": "RD Fine Payment",
			"patron": member.name,
			"amount": amount,
			"status": "Created",
			"provider": PROVIDER,
			"fine_names": names,
		}
	)
	pay.insert(ignore_permissions=True)
	from sok_resdesk.catalogue import base_url

	key_id, key_secret, _hook = _keys()
	payload = rules.link_payload(
		amount,
		pay.name,
		_("Library fines of {0}").format(member.name),
		member.full_name,
		f"{base_url()}/library/loans",
	)
	try:
		r = requests.post(rules.API, json=payload, auth=(key_id, key_secret), timeout=20)
		data = r.json()
	except (requests.RequestException, ValueError):
		data = {}
		r = None
	url = (data.get("short_url") if isinstance(data, dict) else "") or ""
	if not (r is not None and r.status_code in (200, 201) and _safe_link(url)):
		frappe.log_error(
			title="Research Desk: Razorpay did not make a payment link",
			message=f"status {getattr(r, 'status_code', 'no answer')}",  # never the keys or the body
		)
		frappe.delete_doc("RD Fine Payment", pay.name, ignore_permissions=True, force=True)
		frappe.throw(_("Online payment is not available just now. Please pay at the library desk."))
	frappe.db.set_value("RD Fine Payment", pay.name, {"provider_ref": data.get("id") or "", "link_url": url})
	return {"url": url}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def webhook() -> dict:
	"""Razorpay tells us a payment link was paid."""
	body = frappe.request.get_data() if frappe.request else b""
	return process_webhook(body, frappe.get_request_header("X-Razorpay-Signature") or "")


def process_webhook(body: bytes, signature: str) -> dict:
	"""Believed only with the right signature, and only for the amount that was asked."""
	_key, _secret, hook = _keys()
	if not (features.on("lending") and not seams.classified() and hook):
		frappe.throw(_("Not found."), frappe.DoesNotExistError)
	if not rules.valid_signature(body, signature, hook):
		frappe.throw(
			_("Not found."), frappe.DoesNotExistError
		)  # the same answer as "not set up": no hint which
	try:
		event = rules.paid_event(json.loads(body))
	except ValueError:
		event = None
	if not event:
		return {"ok": 1, "ignored": 1}  # another kind of event: nothing to do, and no retry wanted
	ref, paise, payment_id, link_id = event
	pay = frappe.db.get_value(
		"RD Fine Payment",
		ref,
		["name", "status", "amount", "fine_names", "provider_ref"],
		as_dict=True,
		for_update=True,
	)
	if not pay or (pay.provider_ref and link_id and pay.provider_ref != link_id):
		return {"ok": 1, "ignored": 1}  # not a link this site made
	if pay.status == "Paid":
		return {"ok": 1}  # told twice
	if paise != rules.to_paise(pay.amount):
		frappe.log_error(title="Research Desk: a paid link did not match the amount asked", message=ref)
		return {"ok": 1, "mismatch": 1}
	names = (pay.fine_names or "").splitlines()
	still_due = [n for n in names if frappe.db.get_value("RD Fine", n, "status") == "Due"]
	for name in still_due:
		frappe.db.set_value("RD Fine", name, {"status": "Paid", "paid_on": nowdate()})
	if len(still_due) < len(names):  # the desk took payment (or waived) meanwhile: staff may need to refund
		frappe.log_error(
			title="Research Desk: money arrived for fines that were no longer all due: a refund may be needed",
			message=f"{ref} {payment_id}",
		)
	frappe.db.set_value(
		"RD Fine Payment",
		ref,
		{"status": "Paid", "provider_payment_id": payment_id, "paid_on": get_datetime(now_datetime())},
	)
	frappe.db.commit()
	return {"ok": 1}
