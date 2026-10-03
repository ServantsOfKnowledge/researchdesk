"""ARK identifiers and OCR quality scores (core/ark.py, core/ocrquality.py). Pure Python."""

import pytest

from sok_resdesk.core import ark, ocrquality

# -- ARKs ------------------------------------------------------------------------------------------


def test_check_character_matches_noid():
	# the example in the NOID documentation: 13030/xf93gt2 gets the check character q
	assert ark.check_char("13030/xf93gt2") == "q"


def test_minted_arks_are_valid_unique_and_opaque():
	arks = [ark.mint(ark.TEST_NAAN, "b1", n) for n in range(2000)]
	assert len(set(arks)) == len(arks)
	for a in arks[:50]:
		p = ark.parse(a)
		assert p["valid"] and p["naan"] == "99999" and p["name"].startswith("b1")
		assert set(p["name"]) <= set(ark.XDIGITS)
	# neighbouring books don't get neighbouring names
	assert arks[0][:-3] != arks[1][:-3]


def test_scramble_is_a_bijection_on_a_small_space():
	size = ark.BASE**2
	assert sorted(ark.scramble(n, 2) for n in range(size)) == list(range(size))


def test_an_ark_can_be_made_again_under_another_naan():
	for n in (0, 1, 7, 12345, ark.BASE**ark.BLADE_LENGTH - 1):
		test = ark.mint(ark.TEST_NAAN, "b1", n)
		assert ark.counter_of(test, "b1") == n
		real = ark.mint("12345", "b1", n)
		assert ark.parse(real)["name"][:-1] == ark.parse(test)["name"][:-1]  # same name, new check
		assert ark.parse(real)["valid"]


def test_check_character_catches_typos():
	a = ark.mint(ark.TEST_NAAN, "b1", 42)
	name = ark.parse(a)["name"]
	for i in range(len(name) - 1):
		for c in ark.XDIGITS:
			if c != name[i]:
				typo = name[:i] + c + name[i + 1 :]
				assert not ark.parse(f"ark:/99999/{typo}")["valid"]
	swapped = name[0] + name[2] + name[1] + name[3:]
	if swapped != name:
		assert not ark.parse(f"ark:/99999/{swapped}")["valid"]


def test_parse_forms_and_page_qualifiers():
	a = ark.mint("12345", "b1", 7)
	name = ark.parse(a)["name"]
	for form in (a, f"https://library.example/{a}", f"ark:12345/{name}", a.upper().replace("ARK:", "ark:")):
		assert ark.parse(form)["ark"] == a
	p = ark.parse(f"https://library.example/{a}/n42")
	assert p["qualifier"] == "/n42" and ark.leaf_of(p["qualifier"]) == 42
	assert ark.with_leaf(a, 42) == f"{a}/n42"
	assert ark.leaf_of("/p42") is None and ark.leaf_of("") is None
	with pytest.raises(ark.ArkError):
		ark.parse("https://library.example/library/item/x")


def test_naan_and_shoulder_rules():
	with pytest.raises(ark.ArkError):
		ark.mint("123", "b1", 1)  # too short for a NAAN
	with pytest.raises(ark.ArkError):
		ark.mint("99999", "1b", 1)  # a shoulder is letters, then one digit
	with pytest.raises(ark.ArkError):
		ark.mint("99999", "b1", ark.BASE**ark.BLADE_LENGTH)


def test_info_record():
	text = ark.erc("Kanakadasa", "Kirtanegalu", "1950", "https://library.example/library/item/x")
	assert text.startswith("erc:\nwho: Kanakadasa\n") and "when: 1950" in text
	assert "who: (:unav)" in ark.erc("", "t", "", "w")


# -- OCR quality -----------------------------------------------------------------------------------

CLEAN = {
	"Kannada": "ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು ಮತ್ತು ಪದಗಳು. ಇದು ಒಂದು ಪುಸ್ತಕ",
	"Devanagari": "भारत का इतिहास और संस्कृति",
	"Tamil": "தமிழ் இலக்கியம் வரலாறு",
	"Latin": "The history of the Kannada language and its literature.",
}


@pytest.mark.parametrize("script", sorted(CLEAN))
def test_clean_text_scores_high_in_every_script(script):
	q = ocrquality.page_quality(CLEAN[script])
	assert q["score"] >= 90 and q["script"] == script


def test_broken_indic_ocr_scores_low():
	# vowel signs and viramas starting words, Latin inside Kannada words, stray symbols
	q = ocrquality.page_quality("ಕನ X ಡ ಾಕ ್ಕ ಕಿೀ ಕXನ ■■ ��� ಮತ")
	assert q["score"] < ocrquality.LOW


def test_malformed_words():
	assert not ocrquality.word_ok("ಾಕನ")[0]  # starts with a vowel sign
	assert not ocrquality.word_ok("ಕ್ಾ")[0]  # vowel sign after a virama
	assert not ocrquality.word_ok("ಕಾೆ")[0]  # two vowel signs
	assert not ocrquality.word_ok("ಕನXಡ")[0]  # two scripts
	assert ocrquality.word_ok("ಕಾಂತ")[0]  # anusvara after a vowel sign is fine
	assert ocrquality.word_ok("ಕ್ಷ")[0]  # a conjunct
	assert not ocrquality.word_ok("xkcdtrw")[0]  # no vowels


def test_empty_pages_have_no_score_and_books_weigh_by_text():
	assert ocrquality.page_quality("  \n ")["score"] is None
	book = ocrquality.book_quality(
		[{"text": CLEAN["Kannada"] * 5}, {"text": "■ ಾ"}, {"text": ""}, {"text": "ಕನ X ಡ ಾಕ ್ಕ ಕಿೀ ಕXನ ■■"}]
	)
	assert book["scored_pages"] == 3 and book["low_pages"] == 2
	assert book["score"] >= 70 and book["script"] == "Kannada"  # the long clean page counts most
	assert ocrquality.book_quality([])["score"] is None
