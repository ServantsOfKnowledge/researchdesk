"""Online payment of fines through Razorpay payment links: the amounts, the request and the webhook's
signature. Pure Python, so each can be tested without a site or the network.

Razorpay holds the money and the card details; Research Desk only creates a link for what a member owes and
marks the fines paid when Razorpay's signed webhook says the link was paid.
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import ROUND_HALF_UP, Decimal

API = "https://api.razorpay.com/v1/payment_links"
CURRENCY = "INR"


def to_paise(amount) -> int:
	"""Rupees as the whole paise Razorpay wants (no float arithmetic on money)."""
	return int((Decimal(str(amount or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def link_payload(amount, reference: str, description: str, name: str, callback_url: str) -> dict:
	"""The body of a payment link. No email or SMS is sent by Razorpay (Research Desk sends none either)."""
	return {
		"amount": to_paise(amount),
		"currency": CURRENCY,
		"accept_partial": False,
		"reference_id": reference,
		"description": description[:2000],
		"customer": {"name": (name or "")[:100]},
		"notify": {"sms": False, "email": False},
		"reminder_enable": False,
		"callback_url": callback_url,
		"callback_method": "get",
	}


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
	"""Whether `signature` is the HMAC-SHA256 of the raw request body under the webhook secret."""
	if not (body is not None and signature and secret):
		return False
	expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(
		expected.encode(), signature.strip().encode("utf-8", "ignore")
	)  # bytes: any header text


def paid_event(payload: dict) -> tuple[str, int, str, str] | None:
	"""(our reference, paise paid, Razorpay's payment id, the payment link's id) from a `payment_link.paid`
	event; None for any other event, a link that is not fully paid, or one in another currency."""
	if not isinstance(payload, dict) or payload.get("event") != "payment_link.paid":
		return None
	try:
		link = payload["payload"]["payment_link"]["entity"]
		payment = payload["payload"].get("payment", {}).get("entity", {})
		if link.get("status") != "paid" or (link.get("currency") or CURRENCY) != CURRENCY:
			return None
		return (
			str(link["reference_id"]),
			int(link.get("amount_paid") or link["amount"]),
			str(payment.get("id") or ""),
			str(link.get("id") or ""),
		)
	except (KeyError, TypeError, ValueError):
		return None
