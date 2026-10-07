"""The About me page: accessible, locks while loading, and says why a save failed."""

from .conftest import STUB_GLOBALS, axe_violations, page_shell, render_template

FETCH = """
window.fetch = (u) => new Promise((ok) => setTimeout(() => ok({ json: () => Promise.resolve(
  u.includes("profile.mine")
    ? { message: { profile: { organisation: "Acme", kind: "Organisation" }, access_options: ["", "Blind", "Low vision"] } }
    : { exc: "x", _server_messages: JSON.stringify([JSON.stringify({ message: "Website is not valid" })]) }) }), 30));
"""


def _open(page, site):
	body, script = render_template("profile.html")
	html = page_shell(body, f"<script>{STUB_GLOBALS}{FETCH}</script>{script}")
	page.goto(site.write("about_me.html", html))
	page.wait_for_function("document.getElementById('rd-pf').getAttribute('aria-busy') === 'false'")


def test_no_wcag_problems(page, site, axe_js):
	_open(page, site)
	assert axe_violations(page, axe_js) == []


def test_saved_answers_fill_the_form_and_a_failed_save_is_announced(page, site):
	_open(page, site)
	assert page.input_value("[name=organisation]") == "Acme"
	page.click("button[type=submit]")
	page.wait_for_selector("#rd-pf-err:not(:empty)")
	assert "Website is not valid" in page.inner_text("#rd-pf-err")
	assert page.evaluate("document.activeElement.id") == "rd-pf-err"  # focus moves to the problem
	assert page.get_attribute("#rd-pf-err", "role") == "alert"


def test_choices_have_room_to_tap_and_nothing_scrolls_sideways(page, site):
	_open(page, site)
	assert page.evaluate("document.querySelector('.rd-choice').getBoundingClientRect().height") >= 44
	page.set_viewport_size({"width": 360, "height": 800})
	assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
	assert page.errors == []
