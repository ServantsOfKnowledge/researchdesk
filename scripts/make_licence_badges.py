"""Draw the licence badges shown on book pages (sok_resdesk/public/images/licences/*.svg).

Run after changing the design: python scripts/make_licence_badges.py. The badges are simple
88x31 buttons: the Creative Commons mark, then one disc per licence element (BY, NC, ND, SA, 0).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sok_resdesk.core import licence  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "sok_resdesk", "public", "images", "licences")
ELEMENTS = {"by": "BY", "nc": "NC", "nd": "ND", "sa": "SA", "zero": "0", "mark": "PD"}


def svg(code: str) -> str:
	kind, version = code.rsplit("-", 1)
	parts = ["zero"] if kind == "zero" else ["mark"] if kind == "mark" else kind.split("-")
	label = licence.parse(f"https://creativecommons.org/licenses/{kind}/{version}/")
	title = label.name if label else code
	if kind == "zero":
		title = f"CC0 {version} Universal"
	if kind == "mark":
		title = f"Public Domain Mark {version}"
	cx = 19
	body = [
		'<rect x="0.5" y="0.5" width="87" height="30" rx="4" fill="#4a4a4a" stroke="#222"/>',
		'<rect x="1" y="1" width="36" height="29" rx="3.5" fill="#fff"/>',
		f'<circle cx="{cx}" cy="15.5" r="11" fill="#fff" stroke="#222" stroke-width="2.4"/>',
		f'<text x="{cx}" y="19.5" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="11" font-weight="700" fill="#222">cc</text>',
	]
	x = 40
	for p in parts:
		body.append(f'<circle cx="{x + 7}" cy="15.5" r="7.5" fill="#fff"/>')
		body.append(
			f'<text x="{x + 7}" y="18.4" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" '
			f'font-size="8.5" font-weight="700" fill="#222">{ELEMENTS[p]}</text>'
		)
		x += 16
	return (
		'<svg xmlns="http://www.w3.org/2000/svg" width="88" height="31" viewBox="0 0 88 31" role="img" '
		f'aria-label="{title}"><title>{title}</title>' + "".join(body) + "</svg>\n"
	)


def main() -> None:
	os.makedirs(OUT, exist_ok=True)
	for code in licence.all_codes():
		with open(os.path.join(OUT, f"{code}.svg"), "w", encoding="utf-8") as f:
			f.write(svg(code))
	print(f"{len(licence.all_codes())} badges in {os.path.normpath(OUT)}")


if __name__ == "__main__":
	main()
