"""Typing in your own language (ime.js + jquery.ime) on a search box."""

from .conftest import axe_violations, page_shell

PAGE = """
<form role="search"><label for="q">Search</label><input id="q" type="search"></form>
<script src="/jquery.min.js"></script>
<script>window.RD_I18N = { messages: {} };</script>
<script src="/assets/sok_resdesk/js/a11y.js"></script>
<script src="/assets/sok_resdesk/js/ime.js?v=test"></script>
"""


def _open(page, site, lang="kn"):
	page.goto(site.write(f"typing_{lang}.html", page_shell(PAGE, lang=lang)))
	page.wait_for_selector(".rd-ime__btn")


def test_the_control_starts_on_the_portals_language_and_is_off(page, site):
	_open(page, site)
	assert page.input_value(".rd-ime__code") == "kn"
	assert page.get_attribute(".rd-ime__btn", "aria-pressed") == "false"
	page.click("#q")
	page.keyboard.type("abc")
	assert page.input_value("#q") == "abc"  # nothing changes until it is turned on


def test_latin_letters_become_kannada_when_turned_on(page, site):
	_open(page, site)
	page.click(".rd-ime__btn")
	page.wait_for_function("jQuery('#q').data('ime') && jQuery('#q').data('ime').inputmethod")
	page.click("#q")
	page.keyboard.type("kannaDa")
	assert page.input_value("#q") == "ಕನ್ನಡ"
	assert page.get_attribute(".rd-ime__btn", "aria-pressed") == "true"


def test_another_language_by_code_or_name_and_a_clear_message_for_nonsense(page, site):
	_open(page, site)
	page.fill(".rd-ime__code", "hi")
	page.press(".rd-ime__code", "Tab")
	page.wait_for_function("jQuery('#q').data('ime') && jQuery('#q').data('ime').language === 'hi'")
	page.fill("#q", "")
	page.click("#q")
	page.keyboard.type("hindii")
	assert page.input_value("#q") == "हिन्दी"
	page.fill(".rd-ime__code", "zzz")
	page.press(".rd-ime__code", "Tab")
	page.wait_for_function("document.querySelector('.rd-ime__msg').textContent.length > 0")
	assert "zzz" in page.inner_text(".rd-ime__msg")


def test_no_wcag_problems(page, site, axe_js):
	_open(page, site)
	assert axe_violations(page, axe_js) == []
	assert page.errors == []
