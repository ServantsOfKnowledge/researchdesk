"""Romanised words → Indic spellings (core/translit.py)."""

from sok_resdesk.core.translit import candidates, has_indic, is_latin_word, script_of_language

# what readers type → how the word is really spelt; each must be among the candidates search.py
# probes (36: the first 12, then 24 more when none of those is in the catalogue)
KANNADA = {
	"vachana": "ವಚನ",
	"kanakadasa": "ಕನಕದಾಸ",
	"dasa": "ದಾಸ",
	"kannada": "ಕನ್ನಡ",
	"purandara": "ಪುರಂದರ",
	"sangeeta": "ಸಂಗೀತ",
	"basavanna": "ಬಸವಣ್ಣ",
	"karnataka": "ಕರ್ನಾಟಕ",
	"ganga": "ಗಂಗಾ",
	"madhu": "ಮಧು",
	"kavite": "ಕವಿತೆ",
	"mysuru": "ಮೈಸೂರು",
	"sahitya": "ಸಾಹಿತ್ಯ",
	"krishna": "ಕೃಷ್ಣ",
	"kruti": "ಕೃತಿ",
}
DEVANAGARI = {"dharma": "धर्म", "gita": "गीता", "ramayana": "रामायण", "sanskrit": "संस्कृत", "rishi": "ऋषि"}


def test_the_real_spelling_is_among_the_candidates():
	for word, spelt in KANNADA.items():
		assert spelt in candidates(word, "kannada", limit=36), word
	for word, spelt in DEVANAGARI.items():
		assert spelt in candidates(word, "devanagari", limit=36), word


def test_the_usual_reading_comes_first():
	assert candidates("vachana", "kannada")[0] == "ವಚನ"
	assert candidates("purandara", "kannada")[0] == "ಪುರಂದರ"  # n before d: an anusvara
	assert candidates("kannada", "kannada")[0].startswith("ಕನ್ನ")  # a doubled consonant
	assert candidates("dharma", "devanagari")[0] == "धर्म"  # Hindi drops the final vowel


def test_iast_is_read_exactly():
	assert candidates("ṭīkā", "kannada")[0] == "ಟೀಕಾ"
	assert candidates("śāstra", "devanagari")[0] == "शास्त्र"


def test_other_scripts():
	assert candidates("vachana", "telugu")[0] == "వచన"
	assert candidates("vachana", "malayalam")[0] == "വചന"
	assert candidates("vachana", "bengali")[0] == "বচন"
	assert candidates("kanaka", "tamil")[0] == "கநக"  # Tamil folds what it doesn't write
	assert all(c for c in candidates("dharma", "gurmukhi"))  # letters it lacks are swapped


def test_what_is_not_a_romanised_word():
	assert candidates("ವಚನ", "kannada") == []
	assert candidates("x", "kannada") == []
	assert candidates("1950", "kannada") == []
	assert candidates("vachana", "klingon") == []
	assert not is_latin_word("ವಚನ") and is_latin_word("Vachana")
	assert has_indic("a ವಚನ") and not has_indic("vachana")
	assert script_of_language("Kannada") == "kannada" and script_of_language("English") is None
