"""Romanised words → their spellings in Indic scripts, for searching (search.py).

People type Indic words in Latin letters in many ways: *vachana*, *vacana*, *dasa* for ದಾಸ,
*kannada* for ಕನ್ನಡ, *purandara* for ಪುರಂದರ. Latin letters leave things open that the scripts
spell apart: long or short vowels (a/ಾ), dental or retroflex consonants (t/ಟ, d/ಡ, n/ಣ, l/ಳ),
ś or ṣ, an anusvara or a nasal consonant before another consonant, a final vowel or none.

`candidates(word, script)` lists the likely spellings, the most likely first (each less usual
choice costs a point; the cheapest come first). search.py keeps those the catalogue really
contains. IAST (ā ī ū ṭ ḍ ṇ ḷ ś ṣ ṃ ḥ ṛ) is read exactly; plain letters are guessed.

Spellings are built in Devanagari and moved to the other Brahmic scripts, whose Unicode blocks
follow the same order (Kannada = Devanagari + 0x380, Telugu + 0x300…); Tamil, which writes fewer
consonants, folds the others onto the ones it has. Pure Python.
"""

from __future__ import annotations

import heapq
import itertools
import re
import unicodedata

OFFSETS = {
	"devanagari": 0x000,
	"bengali": 0x080,
	"gurmukhi": 0x100,
	"gujarati": 0x180,
	"oriya": 0x200,
	"tamil": 0x280,
	"telugu": 0x300,
	"kannada": 0x380,
	"malayalam": 0x400,
}
DRAVIDIAN = {"kannada", "telugu", "tamil", "malayalam"}  # short e and o are their own letters

# catalogue language → script (languages written in more than one script take the usual one)
LANGUAGE_SCRIPT = {
	"kannada": "kannada",
	"konkani": "kannada",  # most Konkani books here are in Kannada script
	"tulu": "kannada",
	"hindi": "devanagari",
	"marathi": "devanagari",
	"sanskrit": "devanagari",
	"nepali": "devanagari",
	"tamil": "tamil",
	"telugu": "telugu",
	"malayalam": "malayalam",
	"bengali": "bengali",
	"assamese": "bengali",
	"gujarati": "gujarati",
	"punjabi": "gurmukhi",
	"oriya": "oriya",
	"odia": "oriya",
}

CONS = {
	"k": 0x915, "kh": 0x916, "g": 0x917, "gh": 0x918,
	"c": 0x91A, "ch": 0x91B, "j": 0x91C, "jh": 0x91D,
	"T": 0x91F, "Th": 0x920, "D": 0x921, "Dh": 0x922, "N": 0x923,
	"t": 0x924, "th": 0x925, "d": 0x926, "dh": 0x927, "n": 0x928,
	"p": 0x92A, "ph": 0x92B, "b": 0x92C, "bh": 0x92D, "m": 0x92E,
	"y": 0x92F, "r": 0x930, "l": 0x932, "L": 0x933, "v": 0x935,
	"sh": 0x936, "Sh": 0x937, "s": 0x938, "h": 0x939,
}  # fmt: skip
# vowel → (letter, sign after a consonant; None = the inherent a)
VOWELS = {
	"a": (0x905, None), "A": (0x906, 0x93E), "i": (0x907, 0x93F), "I": (0x908, 0x940),
	"u": (0x909, 0x941), "U": (0x90A, 0x942), "R": (0x90B, 0x943),
	"e": (0x90E, 0x946), "E": (0x90F, 0x947), "ai": (0x910, 0x948),
	"o": (0x912, 0x94A), "O": (0x913, 0x94B), "au": (0x914, 0x94C),
}  # fmt: skip
VIRAMA, ANUSVARA, VISARGA = 0x94D, 0x902, 0x903
# Tamil writes no aspirates and few voiced letters
TAMIL = {"kh": "k", "g": "k", "gh": "k", "ch": "c", "jh": "c", "Th": "T", "D": "T", "Dh": "T",
	"th": "t", "d": "t", "dh": "t", "ph": "p", "b": "p", "bh": "p", "R": "ru"}  # fmt: skip
# a letter a script lacks → the nearest one it has
FALLBACK = {"Sh": "sh", "sh": "s", "L": "l", "v": "b", "N": "n", "e": "E", "o": "O"}

IAST = {
	"ā": "aa", "ī": "ii", "ū": "uu", "ṛ": "R", "ṝ": "R", "ē": "E", "ō": "O",
	"ṭ": "T", "ḍ": "D", "ṇ": "N", "ḷ": "L", "ś": "sh", "ṣ": "Sh", "ṃ": "M", "ṁ": "M",
	"ḥ": "H", "ñ": "n", "ṅ": "n",
}  # fmt: skip
LATIN_WORD = re.compile(r"^[a-zāīūṛṝēōṭḍṇḷśṣṃṁḥñṅ]{2,}$")

# Latin spelling → the units it may stand for, each with a cost (0 = the usual reading).
# A unit list may hold several letters (a doubled consonant stays one choice).
V, C = "V", "C"
PATTERNS: dict[str, list[tuple[list[tuple[str, str]], int]]] = {}


def _p(text: str, *alts: tuple[list[tuple[str, str]], int]) -> None:
	PATTERNS[text] = list(alts)


for _t in ("kh", "gh", "jh", "ph", "bh"):
	_p(_t, ([(C, _t)], 0))
_p("chh", ([(C, "ch")], 0))
_p("ch", ([(C, "c")], 0), ([(C, "ch")], 1))
_p("th", ([(C, "t")], 0), ([(C, "th")], 1), ([(C, "Th")], 2))
_p("dh", ([(C, "dh")], 0), ([(C, "Dh")], 2), ([(C, "d")], 2))
_p("sh", ([(C, "sh")], 0), ([(C, "Sh")], 1))
for _t, _alts in {
	"k": ["k"], "q": ["k"], "g": ["g"], "c": ["c"], "j": ["j"], "z": ["j"], "f": ["ph"], "x": ["k"],
	"t": ["t", "T"], "d": ["d", "D"], "n": ["n", "N"], "l": ["l", "L"], "s": ["s", "sh"],
	"p": ["p"], "b": ["b"], "m": ["m"], "y": ["y"], "r": ["r"], "h": ["h"], "v": ["v"], "w": ["v"],
	"T": ["T"], "D": ["D"], "N": ["N"], "L": ["L"], "Sh": ["Sh"],
}.items():  # fmt: skip
	_p(_t, *[([(C, a)], i) for i, a in enumerate(_alts)])
	if len(_t) == 1 and _t.islower():  # doubled: kk, tt, nn, ll… (a geminate keeps one choice)
		_p(_t * 2, *[([(C, a), (C, a)], i) for i, a in enumerate(_alts)])
_p("aa", ([(V, "A")], 0))
_p("ai", ([(V, "ai")], 0))
_p("au", ([(V, "au")], 0))
_p("ou", ([(V, "au")], 0))
_p("ee", ([(V, "I")], 0), ([(V, "E")], 1))
_p("ii", ([(V, "I")], 0))
_p("oo", ([(V, "U")], 0), ([(V, "O")], 1))
_p("uu", ([(V, "U")], 0))
_p("a", ([(V, "a")], 0), ([(V, "A")], 1))
_p("i", ([(V, "i")], 0), ([(V, "I")], 1))
_p("u", ([(V, "u")], 0), ([(V, "U")], 1))
_p("e", ([(V, "e")], 0), ([(V, "E")], 1))
_p("o", ([(V, "o")], 0), ([(V, "O")], 1))
# ri / ru: r and a vowel, or the vowel ṛ (कृष्ण, ಕೃತಿ, संस्कृत)
_p("ri", ([(C, "r"), (V, "i")], 0), ([(V, "R")], 1), ([(C, "r"), (V, "I")], 1))
_p("ru", ([(C, "r"), (V, "u")], 0), ([(C, "r"), (V, "U")], 1), ([(V, "R")], 2))
_p("E", ([(V, "E")], 0))
_p("O", ([(V, "O")], 0))
_p("R", ([(V, "R")], 0))
_p("M", ([("M", "M")], 0))
_p("H", ([("H", "H")], 0))
_LONGEST = sorted(PATTERNS, key=len, reverse=True)


def has_indic(text: str) -> bool:
	return any(0x0900 <= ord(ch) <= 0x0D7F for ch in text)


def is_latin_word(word: str) -> bool:
	return bool(LATIN_WORD.match(word.lower()))


def _normalise(word: str) -> str:
	word = unicodedata.normalize("NFC", word.lower())
	return "".join(IAST.get(ch, ch) for ch in word)


def _tokens(word: str) -> list[list[tuple[list[tuple[str, str]], int]]]:
	"""The word as a list of choices; each choice is [(units, cost)]."""
	out, i = [], 0
	while i < len(word):
		for pat in _LONGEST:
			if word.startswith(pat, i):
				out.append(PATTERNS[pat])
				i += len(pat)
				break
		else:
			return []  # a letter we don't read: not a romanised Indic word

	def kind(k):
		return out[k][0][0][0][0] if 0 <= k < len(out) else None

	for k in range(len(out)):
		units = out[k][0][0]
		# English-style y between consonants ("Mysuru", "Byrappa"): the vowel ai, or i
		if units == [(C, "y")] and kind(k - 1) == C and kind(k + 1) in (C, None):
			out[k] = [([(V, "ai")], 0), ([(V, "i")], 1), *[(u, c + 2) for u, c in out[k]]]
	# a nasal after a vowel and before another consonant: an anusvara (ಂ) as often as not
	for k in range(1, len(out) - 1):
		units = out[k][0][0]
		nxt = out[k + 1][0][0]
		if (
			kind(k - 1) == V
			and len(units) == 1
			and units[0][1] in ("n", "m")
			and nxt[0][0] == C
			and nxt[0][1] not in ("n", "m")
		):
			out[k] = [([("M", "M")], 0), *[(u, c + 1) for u, c in out[k]]]
	return out


def _render(units: list[tuple[str, str]], script: str) -> str | None:
	dravidian = script in DRAVIDIAN
	offset = OFFSETS[script]
	out: list[int] = []
	pending = False  # a consonant waiting for its vowel
	for kind, unit in units:
		if script == "tamil":
			unit = TAMIL.get(unit, unit)
		if kind == V:
			if not dravidian and unit in ("e", "o"):
				unit = unit.upper()
			if unit == "ru":  # Tamil: ṛ as ru
				if pending:
					out.append(VOWELS["u"][1])
				pending = False
				continue
			letter, sign = VOWELS[unit]
			if pending:
				if sign:
					out.append(sign)
			else:
				out.append(letter)
			pending = False
		elif kind == C:
			if pending:
				out.append(VIRAMA)
			out.append(CONS[unit])
			pending = True
		elif unit == "M":
			if pending:  # "nk" read as n + k: the n keeps its inherent vowel
				pending = False
			out.append(ANUSVARA)
		elif unit == "H":
			out.append(VISARGA)
			pending = False
	text = "".join(chr(cp + offset) for cp in out)
	if any(unicodedata.name(ch, None) is None for ch in text):
		return None
	return text


def _fallback(units: list[tuple[str, str]], script: str) -> str | None:
	"""Render, swapping letters the script lacks for the nearest it has."""
	units = list(units)
	for _ in range(3):
		text = _render(units, script)
		if text is not None:
			return text
		units = [(k, FALLBACK.get(u, u)) for k, u in units]
	return None


def candidates(word: str, script: str, limit: int = 12) -> list[str]:
	"""Likely spellings of a romanised word in `script`, the most likely first."""
	if script not in OFFSETS or not is_latin_word(word):
		return []
	choices = _tokens(_normalise(word))
	if not choices:
		return []
	# a final consonant: Hindi-like scripts drop the inherent vowel (राम for "ram"), the
	# Dravidian ones write it with a virama (ಕುಮಾರ್) or end in a vowel (ಕುಮಾರ)
	last_units = choices[-1][0][0]
	if last_units[-1][0] == C:
		final = (
			[([(V, "a")], 0), ([("X", "")], 1)]
			if script not in DRAVIDIAN
			else [([("X", "")], 0), ([(V, "a")], 1), ([(V, "u")], 2)]
		)
		choices = [*choices, final]
	sizes = [len(c) for c in choices]
	seen, out = set(), []
	start = tuple(0 for _ in choices)
	heap = [(0, start)]
	visited = {start}
	while heap and len(out) < limit:
		cost, picks = heapq.heappop(heap)
		units = list(itertools.chain.from_iterable(choices[i][p][0] for i, p in enumerate(picks)))
		text = _fallback([u for u in units if u[0] != "X"], script)
		if text and text not in seen:
			seen.add(text)
			out.append(text)
		for i in range(len(picks)):
			if picks[i] + 1 < sizes[i]:
				nxt = (*picks[:i], picks[i] + 1, *picks[i + 1 :])
				if nxt not in visited:
					visited.add(nxt)
					heapq.heappush(heap, (sum(choices[k][p][1] for k, p in enumerate(nxt)), nxt))
	return out


def script_of_language(label: str) -> str | None:
	return LANGUAGE_SCRIPT.get((label or "").strip().lower())
