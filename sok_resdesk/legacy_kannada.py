"""Old Kannada font text to Unicode (docs/legacy-kannada.md), with the Sanchaya converter.

The engine is JavaScript (vendor/kannada_font_converter, GPL-3.0-or-later, kept apart from this MIT
code) and is run as a separate program by core/legacy_kannada.convert. Used when a PDF's text layer is read (Settings → Convert Old Kannada Fonts) and by `convert_text` for staff.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from sok_resdesk.core import legacy_kannada as rules
from sok_resdesk.core.legacy_kannada import ConverterError, convert

MAX_TEXT = 50_000  # one text by hand (the engine needs about 0.2 s per thousand characters at worst)
BATCH_CHARS = 250_000  # characters per call (core.legacy_kannada.MAX_CHARS is the most one call takes)


def setting_font() -> str | None:
	"""The converter's code for the font chosen in Settings; None when it is Off."""
	return rules.code_for(frappe.db.get_single_value("RD Settings", "legacy_kannada_font"))


def fix_pages(pages: list[dict]) -> list[dict]:
	"""The pages of a PDF's text layer with the ones in an old Kannada font converted, when Settings
	chooses a font. Never stops an ingest: a failed conversion leaves the text as it was (and is logged)."""
	font = setting_font()
	if not font or not pages:
		return pages
	todo = [i for i, p in enumerate(pages) if rules.looks_legacy(p.get("text") or "")]
	if not todo:
		return pages
	out = [dict(p) for p in pages]
	try:
		part, size = [], 0
		for i in [*todo, None]:  # None: flush what is left
			if i is not None and (len(pages[i]["text"]) > rules.MAX_CHARS):
				continue  # one page larger than a whole batch is not text: left as it is
			if part and (i is None or size + len(pages[i]["text"]) > BATCH_CHARS):
				for j, text in zip(part, convert([pages[j]["text"] for j in part], font), strict=True):
					out[j]["text"] = text
				part, size = [], 0
			if i is not None:
				part.append(i)
				size += len(pages[i]["text"])
	except Exception:
		frappe.log_error(title="Research Desk: old Kannada font text could not be converted")
		return pages
	return out


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def convert_text(text: str, font: str = "Nudi / Baraha", direction: str = "a2u") -> str:
	"""Staff tool (Desk → Convert Old Kannada Text): one text, to Unicode or back."""
	frappe.only_for(("System Manager", "SOK Super Admin", "ResDesk Manager", "ResDesk Cataloguer"))
	code = rules.code_for(font)
	if not code:
		frappe.throw(_("Choose one of the fonts in the list."))
	if direction not in ("a2u", "u2a"):
		frappe.throw(_("The direction is a2u (old font to Unicode) or u2a."))
	if not text or len(text) > MAX_TEXT:
		frappe.throw(_("Give a text of up to {0} characters.").format(f"{MAX_TEXT:,}"))
	try:
		return convert([text], code, direction)[0]
	except ConverterError as e:
		frappe.throw(_("The conversion failed: {0}").format(str(e)))
