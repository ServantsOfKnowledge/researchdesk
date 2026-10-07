"""Proofreading's language picker: chips and a code box, not a list of every language."""

from .conftest import STUB_GLOBALS, axe_violations, page_shell

BODY = """
<div id="rd-item" data-item="x"></div>
<section id="rd-pages"><button id="rd-proof-btn" type="button" hidden>Proofread</button>
<figure id="rd-pages-image"><img alt="Page image 1" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></figure>
<div id="rd-pages-text" lang="kn">text</div><p id="rd-pages-status"></p></section>
<script src="/jquery.min.js"></script>
<script>%(globals)s
const AV = { kan: "Kannada", eng: "English", hin: "Hindi", tam: "Tamil", tel: "Telugu", mal: "Malayalam",
  san: "Sanskrit", mar: "Marathi", ben: "Bengali", urd: "Urdu", ara: "Arabic", fra: "French", deu: "German" };
window.fetch = (u) => Promise.resolve({ ok: true, json: () => Promise.resolve({ message: u.includes("languages")
  ? { book: ["kan", "eng"], available: AV }
  : { versions: [], presets: { "Two columns": [{ x: 0, y: 0, w: 50, h: 100, kind: "text" }] }, me: "u@x" } }) });</script>
<script src="/assets/sok_resdesk/js/a11y.js"></script>
<script src="/assets/sok_resdesk/js/ime.js?v=test"></script>
<script src="/assets/sok_resdesk/js/proofread.js"></script>
"""


def _open(page, site):
	page.goto(site.write("proofread.html", page_shell(BODY % {"globals": STUB_GLOBALS}, lang="kn")))
	page.evaluate(
		"document.dispatchEvent(new CustomEvent('rd-page-shown', "
		"{ detail: { leaf: 1, can_proofread: true, text: 'abc', label: '' } }))"
	)
	page.click("#rd-proof-btn")
	page.wait_for_selector("#rd-proof-lang-add")


def _chips(page):
	return page.eval_on_selector_all(".rd-chip", "e => e.map(x => x.textContent.replace('✕', '').trim())")


def test_the_books_languages_are_chips_and_there_is_no_checkbox_list(page, site):
	_open(page, site)
	assert _chips(page) == ["Kannada", "English"]
	assert page.query_selector("#rd-proof-langs input[type=checkbox]") is None


def test_add_by_code_or_name_remove_and_report_problems(page, site):
	_open(page, site)
	page.fill("#rd-proof-lang-add", "tam")
	page.press("#rd-proof-lang-add", "Tab")
	page.fill("#rd-proof-lang-add", "Hindi")
	page.press("#rd-proof-lang-add", "Tab")
	assert _chips(page) == ["Kannada", "English", "Tamil", "Hindi"]
	page.fill("#rd-proof-lang-add", "zz")
	page.press("#rd-proof-lang-add", "Tab")
	assert "No language matches" in page.inner_text("#rd-proof-msg")
	page.fill("#rd-proof-lang-add", "ma")  # mal and mar
	page.press("#rd-proof-lang-add", "Tab")
	assert "Several languages fit" in page.inner_text("#rd-proof-msg")
	page.click("[data-lang-remove=tam]")
	assert _chips(page) == ["Kannada", "English", "Hindi"]
	assert page.evaluate("document.activeElement.id") == "rd-proof-lang-add"


def test_a_zone_takes_its_own_language_by_code(page, site):
	_open(page, site)
	page.click("#rd-zone-add")
	page.fill("[data-zlang='0']", "tel")
	page.press("[data-zlang='0']", "Tab")
	assert page.input_value("[data-zlang='0']") == "tel"


def test_the_language_row_stays_one_line_and_has_no_wcag_problems(page, site, axe_js):
	_open(page, site)
	assert page.evaluate("document.querySelector('#rd-proof-langs').getBoundingClientRect().height") < 60
	assert page.query_selector(".rd-ime") is not None  # typing in your language, beside the text
	assert axe_violations(page, axe_js) == []
	assert page.errors == []
