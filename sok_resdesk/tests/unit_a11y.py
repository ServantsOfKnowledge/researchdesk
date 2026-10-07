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


def _about_me():
	from pathlib import Path

	return (Path(__file__).resolve().parents[1] / "www" / "library" / "profile.html").read_text(
		encoding="utf-8"
	)


def test_about_me_form_names_its_fields_for_browsers_and_readers():
	"""WCAG 1.3.5 (autocomplete tokens), 3.3.1 (a problem is announced), 3.3.2 (limits are said)."""
	html = _about_me()
	assert 'class="rd-form" autocomplete="off"' not in html  # a form-wide "off" blocks the tokens
	for field, token in (
		("organisation", "organization"),
		("role_title", "organization-title"),
		("country", "country-name"),
		("website", "url"),
	):
		assert f'name="{field}"' in html
		assert f'autocomplete="{token}"' in html
	assert 'id="rd-pf-err" role="alert"' in html  # a failed save is announced and takes focus
	for hint in ("rd-pf-h-about", "rd-pf-h-vol", "rd-pf-h-acc"):  # each limit is said and tied to its box
		assert f'aria-describedby="{hint}"' in html and f'id="{hint}"' in html
	assert "lock(true)" in html  # nothing can be typed over the answers that are still arriving
