"""Labels for the leaves of a manuscript or palm-leaf bundle.

Photographs of a bundle are numbered 1, 2, 3… in the order taken, but the leaves are cited as
*folio 12a* (recto/verso, or a/b). Some images are not leaves (a cover, a ruler and colour card at
the start, a label at the end). `labels` works out every image's label from where the leaves
begin and how many sides each leaf shows. Pure Python (no Frappe), unit-tested directly.
"""

from __future__ import annotations

SIDES = {"a/b": ("a", "b"), "r/v": ("r", "v"), "none": ("",)}


def labels(
	total: int, start_image: int = 1, leaves: int = 0, sides: str = "a/b", start_folio: int = 1
) -> dict[int, str]:
	"""{image index (from 0): label} for `total` images.

	`start_image` (counting from 1) is the first image of the first leaf; `leaves` how many images
	are leaves from there (0 = all the rest). Each leaf shows each of `sides` in turn (`a/b`: 1a, 1b,
	2a…; `r/v`: 1r, 1v…; `none`: 1, 2, 3…). Images before the first leaf are *front 1…*, after
	the last *end 1…*.
	"""
	if total <= 0:
		return {}
	pattern = SIDES.get(sides, SIDES["a/b"])
	first = max(1, min(int(start_image or 1), total)) - 1
	count = int(leaves) if leaves and int(leaves) > 0 else total - first
	last = min(total, first + count)
	out: dict[int, str] = {}
	for i in range(first):
		out[i] = f"front {i + 1}"
	for n, i in enumerate(range(first, last)):
		folio = start_folio + n // len(pattern)
		out[i] = f"{folio}{pattern[n % len(pattern)]}"
	for n, i in enumerate(range(last, total)):
		out[i] = f"end {n + 1}"
	return out


def clean(raw) -> dict[int, str]:
	"""Stored labels (JSON text or a dict with string keys) as {int: str}; anything unusable is dropped."""
	import json

	if isinstance(raw, str):
		try:
			raw = json.loads(raw or "{}")
		except ValueError:
			return {}
	out = {}
	for k, v in (raw or {}).items():
		try:
			out[int(k)] = str(v)[:20]
		except (TypeError, ValueError):
			continue
	return out
