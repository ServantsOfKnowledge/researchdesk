"""ARK persistent identifiers: minting, check characters and parsing. Pure Python.

An ARK looks like `ark:/99999/b1x7k2m9q`:

* `99999` is the NAAN, the number the ARK Alliance gives an organisation (99999 is the
  Alliance's test number: ARKs minted under it are for trying things out and are not kept);
* `b1` is the shoulder, a prefix for one kind of thing (books here);
* `x7k2m9` is the blade, opaque on purpose (it says nothing about the book, so it never has to
  change when the book's details do), and `q` a check character that catches a mistyped or
  transposed character (the NOID check-digit algorithm, used by most ARK minters).

A qualifier after the name points inside the object: `ark:/99999/b1x7k2m9q/n42` is leaf 42 (the
43rd page image, counted from 0 as archive.org does). Leaves are used, not printed page numbers,
because printed numbers repeat (roman front matter, plates) and leaf numbers never change.
"""

from __future__ import annotations

import re

# NOID's "extended digits": digits and consonants without l (too like 1), so no words form by chance
XDIGITS = "0123456789bcdfghjkmnpqrstvwxz"
BASE = len(XDIGITS)  # 29, a prime: the check character catches every single-character error
TEST_NAAN = "99999"
DEFAULT_SHOULDER = "b1"
BLADE_LENGTH = 6  # 29**6: about 594 million names per shoulder before the blade grows

_NAAN = re.compile(r"^[0-9bcdfghjkmnpqrstvwxz]{5,}$")
_SHOULDER = re.compile(r"^[bcdfghjkmnpqrstvwxz]+[0-9]$")
_ARK = re.compile(
	r"^(?:https?://[^/]+/)?ark:/?(?P<naan>[0-9bcdfghjkmnpqrstvwxz]+)/(?P<name>[0-9a-z]+)(?P<qualifier>/[^?#]*)?$",
	re.IGNORECASE,
)


class ArkError(ValueError):
	pass


def check_char(text: str) -> str:
	"""NOID check character over `naan/name` (characters outside XDIGITS count as 0)."""
	total = sum(i * (XDIGITS.index(c) if c in XDIGITS else 0) for i, c in enumerate(text, 1))
	return XDIGITS[total % BASE]


def encode(n: int, length: int = BLADE_LENGTH) -> str:
	"""A counter as a blade: base 29 in XDIGITS, left-padded to `length`."""
	if n < 0:
		raise ArkError("counter must not be negative")
	out = ""
	while n:
		n, r = divmod(n, BASE)
		out = XDIGITS[r] + out
	return out.rjust(length, XDIGITS[0])


def scramble(n: int, length: int = BLADE_LENGTH) -> int:
	"""Spread consecutive counters over the blade space, so neighbouring books don't get
	neighbouring names (opaque names). A bijection on 0..29**length-1 (multiplication by a number
	coprime to the size, plus an offset), so no two counters ever share a blade."""
	size = BASE**length
	return (n * _MULTIPLIER + 4093) % size


_MULTIPLIER = 7919 * 104729


def unscramble(m: int, length: int = BLADE_LENGTH) -> int:
	"""The counter a scrambled number came from (the inverse of scramble)."""
	size = BASE**length
	return ((m - 4093) * pow(_MULTIPLIER, -1, size)) % size


def decode(blade: str) -> int:
	n = 0
	for c in blade:
		if c not in XDIGITS:
			raise ArkError(f"{c!r} can't be in an ARK name")
		n = n * BASE + XDIGITS.index(c)
	return n


def counter_of(ark: str, shoulder: str) -> int:
	"""The counter an ARK was minted from (to make it again under another NAAN, keeping its name)."""
	name = parse(ark)["name"]
	if not name.startswith(shoulder):
		raise ArkError(f"{ark} is not on the shoulder {shoulder}")
	return unscramble(decode(name[len(shoulder) : -1]))


def validate_naan(naan: str) -> str:
	naan = (naan or "").strip()
	if not _NAAN.match(naan):
		raise ArkError(f"{naan!r} is not a NAAN (five or more digits, given by the ARK Alliance)")
	return naan


def validate_shoulder(shoulder: str) -> str:
	shoulder = (shoulder or "").strip()
	if not _SHOULDER.match(shoulder):
		raise ArkError(f"{shoulder!r} is not a shoulder (letters ending in one digit, e.g. b1)")
	return shoulder


def mint(naan: str, shoulder: str, counter: int) -> str:
	"""The ARK for the `counter`-th book: ark:/<naan>/<shoulder><blade><check>."""
	naan, shoulder = validate_naan(naan), validate_shoulder(shoulder)
	if counter >= BASE**BLADE_LENGTH:
		raise ArkError("this shoulder is full: choose a new one")
	name = shoulder + encode(scramble(counter))
	return f"ark:/{naan}/{name}{check_char(f'{naan}/{name}')}"


def parse(text: str) -> dict:
	"""Split an ARK (bare, `ark:` or with a resolver in front) into naan, name and qualifier, and
	say whether its check character is right. Raises ArkError when it isn't an ARK at all."""
	m = _ARK.match((text or "").strip())
	if not m:
		raise ArkError(f"{text!r} is not an ARK")
	naan, name = m["naan"].lower(), m["name"].lower()
	qualifier = (m["qualifier"] or "").rstrip("/")
	return {
		"naan": naan,
		"name": name,
		"qualifier": qualifier,
		"ark": f"ark:/{naan}/{name}",
		"valid": check_char(f"{naan}/{name[:-1]}") == name[-1],
	}


def leaf_of(qualifier: str) -> int | None:
	"""The page a qualifier points at (`/n42` → 42), or None."""
	m = re.fullmatch(r"/n(\d{1,5})", qualifier or "")
	return int(m[1]) if m else None


def with_leaf(ark: str, leaf: int) -> str:
	return f"{ark}/n{int(leaf)}"


def erc(who: str, what: str, when: str, where: str) -> str:
	"""The ARK `?info` answer: a kernel metadata record (Electronic Resource Citation)."""

	def clean(value: str) -> str:
		return " ".join(str(value or "(:unav)").split())

	return f"erc:\nwho: {clean(who)}\nwhat: {clean(what)}\nwhen: {clean(when)}\nwhere: {clean(where)}\n"
