"""Accessibility helpers: the language of text for screen readers, and books' accessibility metadata."""

import pytest

from sok_resdesk.core import citations
from sok_resdesk.core.normalize import lang_tag, text_lang


@pytest.mark.parametrize(
	"code, tag",
	[
		("kan", "kn"),
		("hin", "hi"),
		("tam", "ta"),
		("san", "sa"),
		("kok", "kok"),
		("eng", "en"),
		("kn", "kn"),
		("mul", ""),
		("", ""),
		(None, ""),
		("xyz", ""),
	],
)
def test_lang_tags_are_what_browsers_know(code, tag):
	assert lang_tag(code) == tag


def test_text_takes_the_language_of_its_script():
	assert text_lang("ಕನಕದಾಸರ ಕೀರ್ತನೆಗಳು", "eng") == "kn"  # a Kannada title in an English record
	assert text_lang("मराठी पुस्तक", "mar") == "mr"  # Devanagari in a Marathi book stays Marathi
	assert text_lang("मराठी पुस्तक", "kan") == "hi"  # ... else the script's usual language
	assert text_lang("ಕೊಂಕಣಿ", "kok") == "kok"  # Konkani in Kannada script
	assert text_lang("Songs of Kanakadasa", "kan") == ""  # Latin letters: the page's language
	assert text_lang("", "kan") == ""


def test_books_say_how_accessible_they_are():
	book = {"item_id": "x", "title": "T", "has_page_text": True}
	ld = citations.json_ld(book)
	assert ld["accessMode"] == ["visual", "textual"] and "readingOrder" in ld["accessibilityFeature"]
	assert ld["accessibilityHazard"] == ["none"] and "screen reader" in ld["accessibilitySummary"]
	scans = citations.json_ld({"item_id": "y", "title": "T"})
	assert scans["accessMode"] == ["visual"] and scans["accessibilityFeature"] == ["none"]
