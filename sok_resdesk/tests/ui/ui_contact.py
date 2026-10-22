"""The Contact us page: accessible, announces why a send failed, and says thanks."""

from .conftest import STUB_GLOBALS, axe_violations, page_shell, render_template

FAIL = "window.fetch = () => Promise.resolve({ json: () => Promise.resolve({ exc: 'x', _server_messages: JSON.stringify([JSON.stringify({ message: 'Many messages are arriving just now.' })]) }) });"
OK = "window.fetch = (u, o) => { window.sent = JSON.parse(o.body); return Promise.resolve({ json: () => Promise.resolve({ message: { sent: 1 } }) }); };"


def _open(page, site, fetch):
	body, script = render_template("contact.html", intro="", keep_days=365, max_message=2000)
	page.goto(site.write("contact.html", page_shell(body, f"<script>{STUB_GLOBALS}{fetch}</script>{script}")))


def test_no_wcag_problems(page, site, axe_js):
	_open(page, site, OK)
	assert axe_violations(page, axe_js) == []


def test_an_empty_message_is_announced_and_focused_without_calling_the_server(page, site):
	_open(page, site, OK)
	page.click("button[type=submit]")
	assert "write a message" in page.inner_text("#rd-ct-err")
	assert page.evaluate("document.activeElement.id") == "rd-ct-err"
	assert page.get_attribute("[name=message]", "aria-invalid") == "true"
	assert page.evaluate("window.sent") is None


def test_a_refusal_from_the_server_is_shown(page, site):
	_open(page, site, FAIL)
	page.fill("[name=message]", "A message of some length.")
	page.click("button[type=submit]")
	page.wait_for_selector("#rd-ct-err:not(:empty)")
	assert "Many messages" in page.inner_text("#rd-ct-err")


def test_sending_says_thanks_and_sends_the_hidden_field_too(page, site):
	_open(page, site, OK)
	page.fill("[name=full_name]", "Asha")
	page.fill("[name=message]", "A message of some length.")
	page.click("button[type=submit]")
	page.wait_for_selector("#rd-ct-done:not([hidden])")
	assert page.evaluate("document.activeElement.id") == "rd-ct-done"
	assert page.evaluate("window.sent") == {
		"full_name": "Asha",
		"contact": "",
		"message": "A message of some length.",
		"rd_hp": "",
	}


def test_the_form_fits_a_phone_and_the_trap_is_out_of_the_way(page, site):
	_open(page, site, OK)
	page.set_viewport_size({"width": 360, "height": 800})
	assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
	assert page.evaluate("document.querySelector('[name=rd_hp]').getBoundingClientRect().left") < 0
