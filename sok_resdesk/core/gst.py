"""GST on a vendor invoice as plain arithmetic (no Frappe): GSTIN checks, tax per line, and the split into
CGST and SGST (the vendor and the library are in one state) or IGST (they are in two)."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

RATES = ("0", "5", "12", "18", "28")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_FORMAT = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _paise(value) -> Decimal:
	return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def valid_gstin(gstin: str) -> bool:
	"""15 characters in the GSTIN pattern with the right check character."""
	g = (gstin or "").strip().upper()
	if not _FORMAT.match(g):
		return False
	total = 0
	for i, c in enumerate(g[:14]):
		v = _CHARS.index(c) * (1 if i % 2 == 0 else 2)
		total += v // 36 + v % 36
	return _CHARS[(36 - total % 36) % 36] == g[14]


def state_of(gstin: str) -> str:
	"""The two-digit state code a valid GSTIN starts with, else ''."""
	g = (gstin or "").strip().upper()
	return g[:2] if valid_gstin(g) else ""


def supply(library_gstin: str, vendor_gstin: str) -> str:
	"""'intra' (same state), 'inter' (two states) or '' when either GSTIN is missing or wrong."""
	a, b = state_of(library_gstin), state_of(vendor_gstin)
	if not (a and b):
		return ""
	return "intra" if a == b else "inter"


def line(quantity, rate, gst_rate) -> tuple[Decimal, Decimal]:
	"""(taxable value, tax) of one invoice line, each rounded to the paisa."""
	if str(gst_rate or 0) not in RATES:
		raise ValueError(f"GST rate {gst_rate} is not one of {', '.join(RATES)}")
	taxable = _paise(Decimal(str(quantity or 0)) * Decimal(str(rate or 0)))
	return taxable, _paise(taxable * Decimal(str(gst_rate or 0)) / 100)


def totals(lines: list[tuple], kind: str) -> dict:
	"""`lines` are (quantity, rate, gst rate); `kind` is supply(). Tax is added up per line, then split: an
	odd paisa goes to SGST, so CGST + SGST always equals the tax. With `kind` '' the tax is kept whole
	(neither split) until the GSTINs are known."""
	taxable = tax = Decimal("0")
	for q, r, g in lines:
		t, x = line(q, r, g)
		taxable += t
		tax += x
	cgst = sgst = igst = Decimal("0")
	if kind == "intra":
		cgst = _paise(tax / 2)
		sgst = tax - cgst
	elif kind == "inter":
		igst = tax
	return {
		"taxable": float(taxable),
		"tax": float(tax),
		"cgst": float(cgst),
		"sgst": float(sgst),
		"igst": float(igst),
		"total": float(taxable + tax),
	}
